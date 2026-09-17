"""評分流程：硬性淘汰 → 薪資計分 → AI 評分 → 加權總分。"""

from fractions import Fraction
from typing import Any

from job_scoring.llm import LLMClient
from job_scoring.models import (
    CAREER_FIT,
    DIMENSIONS,
    INDUSTRY_FIT,
    SALARY,
    SKILL_MATCH,
    DimensionScore,
    JobScore,
    Preferences,
)
from job_scoring.prompt import build_prompt
from job_scoring.rules import check_hard_filters, round_half_up, score_salary

# 分數未知的維度以此分數（中性）代入，讓每筆職缺都用相同的維度與權重計算，總分才能互相比較
UNKNOWN_SCORE = 3


def compute_total(scores: dict[str, int | None], weights: dict[str, float]) -> int:
    """
    計算所有維度的加權平均（null 以 UNKNOWN_SCORE 代入），換算成 0–100 分。

    :param scores: dict[str, int or None], 維度名稱 → 1–5 分或 None
    :param weights: dict[str, float], 維度名稱 → 權重
    :return: int, 0–100 的總分
    """
    filled = {name: UNKNOWN_SCORE if s is None else s for name, s in scores.items()}
    # 經過 str() 再轉 Fraction，0.4 才會是精確的 2/5，而不是浮點數的近似值
    exact_weights = {name: Fraction(str(w)) for name, w in weights.items()}
    avg = sum((exact_weights[name] * s for name, s in filled.items()), Fraction(0)) / sum(exact_weights.values(), Fraction(0))
    return round_half_up((avg - 1) / 4 * 100)


def score_job(job: dict[str, Any], prefs: Preferences, experience: str, client: LLMClient) -> JobScore:
    """
    對單筆職缺評分；被淘汰的職缺不呼叫 LLM。

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client: LLMClient, LLM client
    :return: JobScore, 評分結果
    :raises LLMError: LLM 呼叫失敗
    :raises pydantic.ValidationError: LLM 回應不符合 schema
    """
    job_no = str(job.get("職缺代碼") or "")
    reasons = check_hard_filters(job, prefs)
    if reasons:
        return JobScore(
            job_no=job_no, eliminated=True, elimination_reasons=reasons,
            dimensions=None, total=None, unknown_dimensions=[], comment=None,
        )

    salary_score, salary_reason = score_salary(job, prefs)
    system, user = build_prompt(job, prefs, experience)
    assessment = client.assess(system, user)

    by_name = {
        CAREER_FIT: DimensionScore(score=assessment.career_fit.score, reason=assessment.career_fit.reason),
        SKILL_MATCH: DimensionScore(score=assessment.skill_match.score, reason=assessment.skill_match.reason),
        INDUSTRY_FIT: DimensionScore(score=assessment.industry_fit.score, reason=assessment.industry_fit.reason),
        SALARY: DimensionScore(score=salary_score, reason=salary_reason),
    }
    dimensions = {name: by_name[name] for name in DIMENSIONS}
    scores = {name: d.score for name, d in dimensions.items()}
    return JobScore(
        job_no=job_no,
        eliminated=False,
        elimination_reasons=[],
        dimensions=dimensions,
        total=compute_total(scores, prefs.weights),
        unknown_dimensions=[name for name, s in scores.items() if s is None],
        comment=assessment.comment,
    )
