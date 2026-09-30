"""組合評分提示詞的測試：以中文變數代入個人資料與職缺內容、空值、$ 的比對、職缺內容快照與重打時附上的錯誤。"""

import pytest
from pydantic import ValidationError

from job_scoring.llm import LLMResponseError
from job_scoring.models import AIAssessment
from job_scoring.prompt import (
    MISSING,
    RETRY_HEADER,
    SNAPSHOT_FIELDS,
    build_prompt,
    retry_feedback,
    snapshot,
    split_template,
    unknown_variables,
    used_variables,
)
from job_scoring.settings import DEFAULTS, TEMPLATE


def test_build_prompt_default_template(ok_job, prefs):
    system, user = build_prompt(ok_job, prefs, "經歷標記-BBB", DEFAULTS[TEMPLATE])

    assert system.startswith("你是一位嚴謹的職涯顧問")
    assert "<!--" not in system + user
    # 送給 AI 的資料包含偏好的目標方向、經歷、職缺的工作內容
    for marker in ["- 目標標記-AAA", "經歷標記-BBB", "工作標記-CCC", "- 喜歡：軟體及網路相關業、金融科技"]:
        assert marker in user
    # 空欄位寫成「（無資料）」
    assert f"- 電腦專長：{MISSING}" in user
    assert "$" not in user


def test_build_prompt_empty_personal_data(ok_job, prefs):
    empty = prefs.model_copy(update={"industry": prefs.industry.model_copy(update={"liked": [], "disliked": []})})
    template = "<!-- SYSTEM -->\n<!-- USER -->\n$喜歡的產業|$不喜歡的產業|$工作經歷|$工作內容"

    _, user = build_prompt({**ok_job, "工作內容": None}, empty, "  ", template)

    assert user == "|".join([MISSING] * 4)


def test_build_prompt_variable_followed_by_chinese(ok_job, prefs):
    template = "<!-- SYSTEM -->\n<!-- USER -->\n$職缺名稱與$公司名稱的比較，花費 $100"

    _, user = build_prompt(ok_job, prefs, "經歷", template)

    assert user == "Python 工程師與甲公司的比較，花費 $100"


def test_split_template():
    assert split_template("註解<!-- SYSTEM -->\n指示\n<!-- USER -->\n資料\n") == ("指示", "資料")
    with pytest.raises(ValueError):
        split_template("<!-- SYSTEM -->沒有 USER")


def test_unknown_and_used_variables():
    text = "$年資、$職缺名稱與$年資，$工作經歷2，$ 空白，$9"

    assert unknown_variables(text) == ["年資"]
    assert used_variables(text) == {"職缺名稱", "工作經歷"}


def test_snapshot_fields(ok_job):
    snap = snapshot(ok_job)

    assert list(snap) == list(SNAPSHOT_FIELDS)
    assert snap["工作內容"] == "工作標記-CCC"
    assert snap["薪資下限"] == 60000


def _validation_error(raw):
    """
    以 AIAssessment 驗證 AI 的原始回應，取得驗證錯誤

    :return: ValidationError
    """
    with pytest.raises(ValidationError) as excinfo:
        AIAssessment.model_validate_json(raw)
    return excinfo.value


def _problems(prompt):
    """
    取出附加的錯誤清單

    :return: list[str], 每一項去掉開頭的「- 」
    """
    return [line[2:] for line in prompt.split(RETRY_HEADER)[1].strip().splitlines()]


def test_retry_feedback_keeps_prompt_and_separates_errors():
    error = _validation_error(
        '{"career_fit": {"score": 6, "reason": "a"}, "skill_match": {"score": 1, "reason": "b"},'
        ' "industry_fit": {"score": 1, "reason": "c"}, "comment": "總評"}'
    )

    prompt = retry_feedback("原本的提示詞\n## 工作內容\n工作標記-CCC", error)

    assert prompt.startswith("原本的提示詞\n## 工作內容\n工作標記-CCC\n\n---\n\n# 上一次的回應沒有通過檢查\n")
    assert _problems(prompt) == ["career_fit.score：要是 1–5 的整數或 null（收到：6）"]


def test_retry_feedback_describes_each_error():
    error = _validation_error(
        '{"career_fit": {"score": 4, "reason": "a"}, "skill_match": {"score": null, "reason": " "},'
        ' "industry_fit": {"score": "高", "reason": "c"}}'
    )

    assert _problems(retry_feedback("u", error)) == [
        "skill_match.reason：不可為空字串或只有空白（收到：「 」）",
        "industry_fit.score：要是 1–5 的整數或 null（收到：「高」）",
        "comment：缺少這個欄位",
    ]


@pytest.mark.parametrize("raw, expected", [
    ('{"career_fit": {"score": 4, "reason": "被截斷',
     "整份回應：不是合法的 JSON（EOF while parsing a string at line 1 column 48）"),
    ('"抱歉，我無法評分"', "整份回應：要是 JSON 物件"),
    ("[1, 2]", "整份回應：要是 JSON 物件"),
])
def test_retry_feedback_whole_response_omits_content(raw, expected):
    # 錯誤不屬於任何欄位時，收到的值就是整份回應，不附內容
    assert _problems(retry_feedback("u", _validation_error(raw))) == [expected]


def test_retry_feedback_value_on_one_line():
    error = _validation_error(
        '{"career_fit": [4, "a"], "skill_match": {"score": 4, "reason": "\\n\\n"},'
        ' "industry_fit": {"score": 4, "reason": "c"}, "comment": "總評"}'
    )

    # 物件或陣列也附上收到的值；換行被跳脫，一個問題一行
    assert _problems(retry_feedback("u", error)) == [
        'career_fit：要是 JSON 物件（收到：[4, "a"]）',
        "skill_match.reason：不可為空字串或只有空白（收到：「\\n\\n」）",
    ]


def test_retry_feedback_truncates_long_value():
    error = _validation_error(
        '{"career_fit": {"score": 4, "reason": "a"}, "skill_match": {"score": 4, "reason": "b"},'
        ' "industry_fit": {"score": 4, "reason": "c"}, "comment": ' + "1" * 200 + "}"
    )

    [problem] = _problems(retry_feedback("u", error))

    assert problem.startswith("comment：")
    assert problem.endswith("…）")
    assert len(problem) < 150


def test_retry_feedback_empty_response():
    prompt = retry_feedback("u", LLMResponseError("Gemini 沒有回傳文字（status: completed）"))

    assert _problems(prompt) == ["上一次的回應是空的"]
