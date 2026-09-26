"""組合評分提示詞的測試：以中文變數代入個人資料與職缺內容、空值、$ 的比對與職缺內容快照。"""

import pytest

from job_scoring.prompt import (
    MISSING,
    SNAPSHOT_FIELDS,
    build_prompt,
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
