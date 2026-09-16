"""組合評分提示詞（job-scoring.md §8.2）。模板放在 prompts/scoring.md，和程式碼分開。"""

from pathlib import Path
from string import Template
from typing import Any

from job_scoring.models import Preferences

TEMPLATE_PATH = Path(__file__).parent / "prompts" / "scoring.md"
SYSTEM_MARKER = "<!-- SYSTEM -->"
USER_MARKER = "<!-- USER -->"
MISSING = "（無資料）"


def _load_template() -> tuple[Template, Template]:
    """
    讀取提示詞模板，依 SYSTEM / USER 標記拆成兩段（標記之前的內容是模板註解，捨棄）

    :return: tuple (Template, Template), (system 模板, user 模板)
    """
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    _, rest = text.split(SYSTEM_MARKER, 1)
    system, user = rest.split(USER_MARKER, 1)
    return Template(system.strip()), Template(user.strip())


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


def _join(items: list[str]) -> str:
    """
    把清單以頓號串接；空清單時顯示「（無）」

    :param items: list[str], 要串接的字串
    :return: str, 串接結果
    """
    return "、".join(items) if items else "（無）"


def build_prompt(job: dict[str, Any], prefs: Preferences, experience: str) -> tuple[str, str]:
    """
    組合評分用的 system 與 user 提示詞。薪資與淘汰條件由程式判斷，不放進提示詞。

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :return: tuple (str, str), (system 提示詞, user 提示詞)
    """
    system, user = _load_template()
    user_text = user.substitute(
        goals="\n".join(f"- {g}" for g in prefs.goals),
        liked=_join(prefs.industry.liked),
        disliked=_join(prefs.industry.disliked),
        experience=experience,
        job_name=_field(job.get("職缺名稱")),
        company=_field(job.get("公司名稱")),
        industry=_field(job.get("產業類別")),
        skills=_field(job.get("電腦專長")),
        majors=_field(job.get("科系要求")),
        description=_field(job.get("工作內容")),
    )
    return system.substitute(), user_text
