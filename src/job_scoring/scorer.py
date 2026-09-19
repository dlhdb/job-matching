"""評分流程：硬性淘汰 → 薪資計分 → AI 評分 → 加權總分。"""

import sqlite3
from datetime import datetime
from fractions import Fraction
from typing import Any, Callable

from job_db import load_cached_result, save_score
from job_scoring.llm import LLMClient
from job_scoring.models import (
    CAREER_FIT,
    DIMENSIONS,
    INDUSTRY_FIT,
    SALARY,
    SKILL_MATCH,
    AIAssessment,
    DimensionScore,
    JobScore,
    Preferences,
)
from job_scoring.prompt import build_prompt, cache_key
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


def _eliminated_score(job_no: str, reasons: list[str]) -> JobScore:
    """
    被淘汰職缺的評分結果：沒有維度、總分與評語

    :param job_no: str, 職缺代碼
    :param reasons: list[str], 淘汰原因
    :return: JobScore, 評分結果
    """
    return JobScore(
        job_no=job_no, eliminated=True, elimination_reasons=reasons,
        dimensions=None, total=None, unknown_dimensions=[], comment=None,
    )


def _combine(job: dict[str, Any], prefs: Preferences, assessment: AIAssessment) -> JobScore:
    """
    以 AI 的三個維度加上薪資分數，組成沒被淘汰職缺的評分結果並計算總分

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param assessment: AIAssessment, AI 的評分（新呼叫或沿用上次的）
    :return: JobScore, 評分結果
    """
    salary_score, salary_reason = score_salary(job, prefs)
    by_name = {
        CAREER_FIT: DimensionScore(score=assessment.career_fit.score, reason=assessment.career_fit.reason),
        SKILL_MATCH: DimensionScore(score=assessment.skill_match.score, reason=assessment.skill_match.reason),
        INDUSTRY_FIT: DimensionScore(score=assessment.industry_fit.score, reason=assessment.industry_fit.reason),
        SALARY: DimensionScore(score=salary_score, reason=salary_reason),
    }
    dimensions = {name: by_name[name] for name in DIMENSIONS}
    scores = {name: d.score for name, d in dimensions.items()}
    return JobScore(
        job_no=str(job.get("職缺代碼") or ""),
        eliminated=False,
        elimination_reasons=[],
        dimensions=dimensions,
        total=compute_total(scores, prefs.weights),
        unknown_dimensions=[name for name, s in scores.items() if s is None],
        comment=assessment.comment,
    )


def _assessment_from_result(result: dict[str, Any]) -> AIAssessment:
    """
    從存下的評分結果（中文鍵名）還原 AI 的三個維度與評語

    :param result: dict, 上次評分寫入資料庫的完整評分結果
    :return: AIAssessment, 上次的 AI 評分
    :raises pydantic.ValidationError: 存下的內容不符合 AI 輸出的 schema
    """
    dimensions = result.get("維度") or {}

    def _dimension(name: str) -> dict[str, Any]:
        stored = dimensions.get(name) or {}
        return {"score": stored.get("分數"), "reason": stored.get("理由")}

    return AIAssessment.model_validate({
        "career_fit": _dimension(CAREER_FIT),
        "skill_match": _dimension(SKILL_MATCH),
        "industry_fit": _dimension(INDUSTRY_FIT),
        "comment": result.get("評語"),
    })


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
    reasons = check_hard_filters(job, prefs)
    if reasons:
        return _eliminated_score(str(job.get("職缺代碼") or ""), reasons)
    system, user = build_prompt(job, prefs, experience)
    return _combine(job, prefs, client.assess(system, user))


def score_and_save(
    job: dict[str, Any],
    prefs: Preferences,
    experience: str,
    client_factory: Callable[[], LLMClient],
    conn: sqlite3.Connection,
    provider: str,
    model: str,
) -> tuple[JobScore, bool]:
    """
    對單筆職缺評分並寫入 job_scores；評分失敗時例外直接往外拋，資料庫中原本的列不變。

    送給 AI 的內容與上次相同（快取鍵相同）時，沿用上次的 AI 維度與評語，不呼叫 AI；
    淘汰、薪資分數與總分每次都重算。

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client_factory: callable, 取得 LLM client；只有真的要呼叫 AI 時才呼叫
    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param provider: str, client_factory 使用的 LLM 供應商
    :param model: str, client_factory 使用的模型名稱
    :return: tuple (JobScore, bool), (評分結果, 是否沿用上次的 AI 評分)
    :raises ValueError: client_factory 不認得供應商
    :raises LLMError: 建立 client 或 LLM 呼叫失敗
    :raises pydantic.ValidationError: LLM 回應或沿用的評分不符合 schema
    :raises sqlite3.Error: 讀寫資料庫失敗
    """
    job_no = str(job.get("職缺代碼") or "")
    reasons = check_hard_filters(job, prefs)
    # 被淘汰的職缺沒有呼叫 AI，不需要快取鍵，也沒有使用任何 LLM
    key: str | None = None
    used_provider: str | None = None
    used_model: str | None = None
    reused = False
    if reasons:
        score = _eliminated_score(job_no, reasons)
    else:
        system, user = build_prompt(job, prefs, experience)
        key, used_provider, used_model = cache_key(provider, model, system, user), provider, model
        cached = load_cached_result(conn, job_no, key)
        reused = cached is not None
        if cached is not None:
            assessment = _assessment_from_result(cached)
        else:
            assessment = client_factory().assess(system, user)
        score = _combine(job, prefs, assessment)

    save_score(
        conn,
        job_no=score.job_no,
        scored_at=datetime.now(),
        eliminated=score.eliminated,
        total=score.total,
        comment=score.comment,
        result=score.model_dump(by_alias=True),
        cache_key=key,
        provider=used_provider,
        model=used_model,
    )
    return score, reused
