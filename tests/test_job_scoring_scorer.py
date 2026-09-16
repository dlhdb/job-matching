"""工作評分（F1-01）評分流程的測試：總分計算（AC-3）與評分流程、AI 回應處理（AC-4）。"""

import pytest
from pydantic import ValidationError

from job_scoring.models import AIAssessment
from job_scoring.scorer import compute_total, score_job

WEIGHTS = {"職涯方向契合度": 0.4, "技能匹配度": 0.25, "產業公司吸引力": 0.15, "薪資水準": 0.2}
DIMENSION_NAMES = ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準"]


# PRD AC-3 表格：(職涯方向, 技能, 產業公司, 薪資, 預期總分)
@pytest.mark.parametrize("career, skill, industry, salary, expected", [
    (5, 5, 5, 5, 100),
    (1, 1, 1, 1, 0),
    (4, 4, 5, 4, 79),
    (5, 3, None, None, 70),        # 未知維度以 3 分代入
    (None, None, None, None, 50),  # 全部未知，等同全部 3 分
])
def test_compute_total(career, skill, industry, salary, expected):
    scores = dict(zip(DIMENSION_NAMES, [career, skill, industry, salary]))

    assert compute_total(scores, WEIGHTS) == expected


def test_score_job_eliminated_skips_llm(out_job, prefs, fake_client):
    result = score_job(out_job, prefs, "經歷", fake_client)

    assert fake_client.calls == []
    assert result.eliminated is True
    assert result.elimination_reasons
    assert result.dimensions is None
    assert result.total is None


def test_score_job_ok(ok_job, prefs, fake_client):
    result = score_job(ok_job, prefs, "經歷", fake_client)
    data = result.model_dump(by_alias=True)

    assert len(fake_client.calls) == 1
    assert list(data["維度"]) == DIMENSION_NAMES
    assert data["維度"]["技能匹配度"]["分數"] is None
    assert data["維度"]["薪資水準"]["分數"] == 4
    assert data["總分"] == 75
    assert data["未知維度"] == ["技能匹配度"]
    assert data["評語"] == "總評"
    assert data["淘汰"] is False
    assert data["淘汰原因"] == []


def test_score_job_multiple_unknown_dimensions(ok_job, prefs, make_client):
    client = make_client(career=None, skill=None)

    data = score_job(ok_job, prefs, "經歷", client).model_dump(by_alias=True)

    assert data["總分"] == 55
    assert data["未知維度"] == ["職涯方向契合度", "技能匹配度"]
    assert data["評語"] == "總評"


def test_score_job_rejects_out_of_range_score():
    response = {
        "career_fit": {"score": 6, "reason": "r"},
        "skill_match": {"score": None, "reason": "r"},
        "industry_fit": {"score": 3, "reason": "r"},
        "comment": "總評",
    }

    with pytest.raises(ValidationError):
        AIAssessment.model_validate(response)
