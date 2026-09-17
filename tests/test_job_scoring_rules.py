"""工作評分程式規則的測試：薪資計分與硬性淘汰。"""

import pytest

from job_scoring.profile import load_preferences
from job_scoring.rules import check_hard_filters, score_salary

# (薪資待遇, 下限, 上限, 預期薪資分數)，這些職缺都不會被淘汰
SALARY_CASES = [
    ("月薪70,000~90,000元", 70000, 90000, 5),
    ("月薪60,000~80,000元", 60000, 80000, 4),
    ("月薪56,000~60,000元", 56000, 60000, 2),
    ("年薪980,000~1,260,000元", 980000, 1260000, 5),
    ("月薪50,000元以上", 50000, 9999999, 2),
    ("待遇面議", 0, 0, None),
    ("時薪500元以上", 500, 9999999, None),
    ("論件計酬3,000~15,000元", 3000, 15000, None),
    (None, None, None, None),
]


def _salary_job(make_job, text, low, high, **overrides):
    return make_job(**{"薪資待遇": text, "薪資下限": low, "薪資上限": high}, **overrides)


@pytest.mark.parametrize("text, low, high, expected", SALARY_CASES)
def test_score_salary_table(make_job, prefs, text, low, high, expected):
    job = _salary_job(make_job, text, low, high)

    score, reason = score_salary(job, prefs)

    assert score == expected
    assert reason
    assert check_hard_filters(job, prefs) == []


@pytest.mark.parametrize("text, low, high", [
    ("月薪40,000~50,000元", 40000, 50000),
    ("年薪560,000~700,000元", 560000, 700000),
])
def test_check_hard_filters_salary_below_floor(make_job, prefs, text, low, high):
    reasons = check_hard_filters(_salary_job(make_job, text, low, high), prefs)

    assert len(reasons) == 1
    assert "底線" in reasons[0]


def test_check_hard_filters_collects_all_reasons(make_job, prefs):
    job = _salary_job(make_job, "月薪40,000~50,000元", 40000, 50000,
                      **{"職缺名稱": "業務專員", "公司名稱": "乙公司"})

    reasons = check_hard_filters(job, prefs)

    assert len(reasons) == 3
    assert any("乙公司" in r for r in reasons)
    assert any("業務" in r for r in reasons)
    assert any("底線" in r for r in reasons)


def test_check_hard_filters_title_keyword_case_insensitive(make_job, preferences_data, write_profile):
    preferences_data["淘汰條件"]["職稱關鍵字"] = ["sales"]
    prefs = load_preferences(write_profile(preferences_data) / "preferences.yaml")

    assert check_hard_filters(make_job(**{"職缺名稱": "Senior SALES Manager"}), prefs) == ["職稱含排除關鍵字：sales"]
