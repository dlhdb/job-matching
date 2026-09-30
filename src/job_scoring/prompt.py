"""由提示詞模板組合評分提示詞。模板是使用者在設定頁編輯的文字，以 $變數 放入個人資料與職缺內容。"""

import json
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from job_scoring.llm import LLMResponseError
from job_scoring.models import Preferences

SYSTEM_MARKER = "<!-- SYSTEM -->"
USER_MARKER = "<!-- USER -->"
MISSING = "（無資料）"

PERSONAL_VARIABLES = ("目標方向", "喜歡的產業", "不喜歡的產業", "工作經歷")
JOB_VARIABLES = ("職缺名稱", "公司名稱", "產業類別", "電腦專長", "科系要求", "工作內容")
VARIABLES = PERSONAL_VARIABLES + JOB_VARIABLES

# 比對時長的名稱優先，一個名稱是另一個的開頭時才不會被短的搶先
_BY_LENGTH = sorted(VARIABLES, key=len, reverse=True)

# 重打時附在 user 提示詞後的錯誤說明：以分隔線與標題和資料分開，AI 才不會把它當成職缺內容的一部分
RETRY_HEADER = (
    "---\n\n# 上一次的回應沒有通過檢查\n\n"
    "以上是評分用的資料，內容沒有變。你上一次的回應有以下問題，請修正後依相同格式重新回應："
)
# 錯誤說明中「收到的值」最多列出幾個字，避免把過長的欄位值塞回提示詞
MAX_INPUT_CHARS = 80

# 送評時的職缺內容快照：送進 AI 的欄位，加上計算薪資分數與淘汰用的欄位
SNAPSHOT_FIELDS = ("職缺名稱", "公司名稱", "產業類別", "電腦專長", "科系要求", "工作內容", "薪資待遇", "薪資下限", "薪資上限")


def split_template(text: str) -> tuple[str, str]:
    """
    依 SYSTEM、USER 標記把模板拆成兩段；SYSTEM 標記之前的內容是模板的註解，捨棄

    :param text: str, 提示詞模板
    :return: tuple (str, str), (system 段, user 段)，都去除頭尾空白
    :raises ValueError: 缺少標記，或 USER 標記在 SYSTEM 之前
    """
    system_at, user_at = text.find(SYSTEM_MARKER), text.find(USER_MARKER)
    if system_at < 0 or user_at < 0:
        raise ValueError(f"缺少 {SYSTEM_MARKER} 或 {USER_MARKER} 標記")
    if user_at < system_at:
        raise ValueError(f"{SYSTEM_MARKER} 要在 {USER_MARKER} 前面")
    return text[system_at + len(SYSTEM_MARKER):user_at].strip(), text[user_at + len(USER_MARKER):].strip()


def _scan(text: str) -> list[tuple[int, int, str | None]]:
    """
    找出文字中的 $變數

    中文沒有空白分隔，所以不用 string.Template 的規則，而是在 $ 之後以已知的變數名稱比對（長的優先）。
    $ 之後接文字、卻不是已知的變數時，算不認得的變數，名稱取到第一個不是文字的字元為止；
    其他的 $（例如接數字或空白）原樣保留。

    :param text: str, 模板的文字
    :return: list[tuple], 每個變數的 (開始位置, 結束位置, 已知的變數名稱)；不認得的變數名稱為 None
    """
    found: list[tuple[int, int, str | None]] = []
    i = text.find("$")
    while i >= 0:
        rest = text[i + 1:]
        name = next((n for n in _BY_LENGTH if rest.startswith(n)), None)
        if name is not None:
            found.append((i, i + 1 + len(name), name))
        elif rest[:1].isalpha() or rest[:1] == "_":
            end = i + 1
            while end < len(text) and (text[end].isalpha() or text[end] == "_"):
                end += 1
            found.append((i, end, None))
        i = text.find("$", i + 1)
    return found


def unknown_variables(text: str) -> list[str]:
    """
    列出不認得的變數，依第一次出現的順序、不重複

    :param text: str, 模板的文字
    :return: list[str], 變數名稱（不含 $）
    """
    names = [text[start + 1:end] for start, end, name in _scan(text) if name is None]
    return list(dict.fromkeys(names))


def used_variables(text: str) -> set[str]:
    """
    :param text: str, 模板的文字
    :return: set[str], 用到的已知變數名稱（不含 $）
    """
    return {name for _, _, name in _scan(text) if name is not None}


def _substitute(text: str, values: dict[str, str]) -> str:
    """
    把已知的變數換成對應的值，其他文字原樣保留

    :param text: str, 模板的一段
    :param values: dict, 變數名稱 → 值
    :return: str, 代入後的文字
    """
    parts, last = [], 0
    for start, end, name in _scan(text):
        if name is not None:
            parts += [text[last:start], values[name]]
            last = end
    parts.append(text[last:])
    return "".join(parts)


def _field(value: Any) -> str:
    """
    把職缺欄位轉成提示詞用的字串；null 或空字串時明確標示為「（無資料）」

    :param value: Any, 職缺欄位值
    :return: str, 提示詞用的字串
    """
    if value is None:
        return MISSING
    text = str(value).strip()
    return text or MISSING


def _join(items: list[str], separator: str) -> str:
    """
    把清單串接成一段文字；空清單時放入「（無資料）」

    :param items: list[str], 要串接的字串
    :param separator: str, 分隔字串
    :return: str, 串接結果
    """
    return separator.join(items) if items else MISSING


def snapshot(job: dict[str, Any]) -> dict[str, Any]:
    """
    取出送評時的職缺內容快照

    :param job: dict, 符合職缺欄位契約的單筆職缺
    :return: dict, SNAPSHOT_FIELDS 的欄位與值
    """
    return {name: job.get(name) for name in SNAPSHOT_FIELDS}


def build_prompt(job: dict[str, Any], prefs: Preferences, experience: str, template: str) -> tuple[str, str]:
    """
    以模板組合評分用的 system 與 user 提示詞。薪資與淘汰條件由程式判斷，沒有對應的變數。

    :param job: dict, 符合職缺欄位契約的單筆職缺（或職缺內容快照）
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :param template: str, 通過檢查的提示詞模板
    :return: tuple (str, str), (system 提示詞, user 提示詞)
    :raises ValueError: 模板缺少標記或標記順序顛倒
    """
    system, user = split_template(template)
    values = {
        "目標方向": _join([f"- {goal}" for goal in prefs.goals], "\n"),
        "喜歡的產業": _join(prefs.industry.liked, "、"),
        "不喜歡的產業": _join(prefs.industry.disliked, "、"),
        "工作經歷": _field(experience),
        **{name: _field(job.get(name)) for name in JOB_VARIABLES},
    }
    return _substitute(system, values), _substitute(user, values)


def _describe_error(error: ErrorDetails) -> str:
    """
    把一項 Pydantic 驗證錯誤寫成給 AI 看的一行中文說明：哪個欄位、錯在哪、收到的值

    :param error: ErrorDetails, ValidationError.errors() 的一項
    :return: str, 例如「career_fit.score：要是 1–5 的整數或 null（收到：6）」
    """
    loc = error["loc"]
    if not loc:
        # 整份回應的格式不對：收到的值就是整份回應，不附內容，只寫錯在哪
        if error["type"] == "json_invalid":
            # Pydantic 的訊息寫出在哪個位置出錯，例如 EOF while parsing a string at line 1 column 57
            return f"整份回應：不是合法的 JSON（{error['msg'].removeprefix('Invalid JSON: ')}）"
        return f"整份回應：{_message(error)}"
    field = ".".join(str(part) for part in loc)
    if error["type"] == "missing":
        return f"{field}：缺少這個欄位"
    message = "要是 1–5 的整數或 null" if loc[-1] == "score" else _message(error)
    # 以 JSON 寫出收到的值：換行等控制字元會被跳脫，一個問題才維持一行
    value = error["input"]
    text = f"「{json.dumps(value, ensure_ascii=False)[1:-1]}」" if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "…"
    return f"{field}：{message}（收到：{text}）"


def _message(error: ErrorDetails) -> str:
    """
    Pydantic 驗證錯誤的說明，常見的改寫成中文，其他保留原文

    :param error: ErrorDetails, ValidationError.errors() 的一項
    :return: str, 錯在哪
    """
    if error["type"] == "model_type":
        return "要是 JSON 物件"
    if error["type"] == "value_error":
        # validator 自己的訊息，不帶 Pydantic 加上的「Value error, 」前綴
        return str(error["ctx"]["error"])
    return error["msg"]


def retry_feedback(user: str, error: LLMResponseError | ValidationError) -> str:
    """
    AI 回應不能用而重打時，在第一次的 user 提示詞後面附上上一次的錯誤清單。

    送一樣的提示詞時，AI 不知道上一次錯在哪，容易再犯同樣的錯，所以把沒通過檢查的原因告訴它。
    只附錯誤清單、不附上一次的完整回應：錯誤清單已經帶著錯的值，不必改 LLM client 的介面讓它交出原始文字。
    評分依據的提示詞由模板與職缺快照組回，不含這段附加的文字：附加的只是「請修正」，評分用的資料不變。

    :param user: str, 第一次送出的 user 提示詞
    :param error: LLMResponseError or ValidationError, 上一次的回應沒有文字，或不符合 schema
    :return: str, 附上錯誤清單的 user 提示詞
    """
    if isinstance(error, ValidationError):
        problems = [_describe_error(e) for e in error.errors(include_url=False)]
    else:
        problems = ["上一次的回應是空的"]
    items = "\n".join(f"- {problem}" for problem in problems)
    return f"{user}\n\n{RETRY_HEADER}\n\n{items}"
