"""評分流程：硬性淘汰 → 薪資計分 → AI 評分 → 加權總分。"""

import sqlite3
from datetime import datetime
from fractions import Fraction
from typing import Any

from job_db import save_auto_score
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


def _eliminated_score(job_no: str, reasons: list[str]) -> JobScore:
    """
    被淘汰職缺的評分結果：沒有維度與總分，評語由淘汰原因組成

    :param job_no: str, 職缺代碼
    :param reasons: list[str], 淘汰原因
    :return: JobScore, 評分結果
    """
    return JobScore(
        job_no=job_no, eliminated=True, elimination_reasons=reasons,
        dimensions=None, total=None, unknown_dimensions=[], comment="淘汰：" + "；".join(reasons),
    )


def _combine(job: dict[str, Any], prefs: Preferences, assessment: AIAssessment) -> JobScore:
    """
    以 AI 的三個維度加上薪資分數，組成沒被淘汰職缺的評分結果並計算總分

    :param job: dict, 符合職缺欄位契約的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param assessment: AIAssessment, AI 的評分
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


def score_job(job: dict[str, Any], prefs: Preferences, experience: str, client: LLMClient | None) -> JobScore:
    """
    對單筆職缺評分；被淘汰的職缺不呼叫 LLM。

    :param job: dict, 符合職缺欄位契約的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client: LLMClient or None, LLM client；呼叫端確定這筆會被淘汰時才可以是 None
    :return: JobScore, 評分結果
    :raises LLMError: LLM 呼叫失敗
    :raises pydantic.ValidationError: LLM 回應不符合 schema
    :raises ValueError: 沒被淘汰卻沒有提供 client，代表呼叫端的程式錯誤
    """
    reasons = check_hard_filters(job, prefs)
    if reasons:
        return _eliminated_score(str(job.get("職缺代碼") or ""), reasons)
    if client is None:
        raise ValueError(f"職缺 {job.get('職缺代碼')} 需要呼叫 AI，但沒有提供 LLM client")
    system, user = build_prompt(job, prefs, experience)
    return _combine(job, prefs, client.assess(system, user))


def score_and_save(
    job: dict[str, Any],
    prefs: Preferences,
    experience: str,
    client: LLMClient | None,
    conn: sqlite3.Connection | None,
    provider: str,
    model: str,
) -> JobScore:
    """
    對單筆職缺評分並新增一筆自動評分紀錄；評分失敗時例外直接往外拋，不寫入。
    每次都重新評分，沒被淘汰的職缺一律呼叫 AI。

    conn 為 None 時是試跑：只評分，不寫入資料庫。

    :param job: dict, 符合職缺欄位契約的單筆職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client: LLMClient or None, LLM client；整批都會被淘汰時可以是 None
    :param conn: sqlite3.Connection or None, open_db 開啟的連線；None 表示試跑
    :param provider: str, client 使用的 LLM 供應商
    :param model: str, client 使用的模型名稱
    :return: JobScore, 評分結果
    :raises LLMError: LLM 呼叫失敗
    :raises pydantic.ValidationError: LLM 回應不符合 schema
    :raises sqlite3.Error: 寫入資料庫失敗
    """
    score = score_job(job, prefs, experience, client)
    if conn is None:
        return score
    # 被淘汰的職缺沒有呼叫 AI，也就沒有使用任何 LLM
    save_auto_score(
        conn,
        job_no=score.job_no,
        scored_at=datetime.now(),
        eliminated=score.eliminated,
        total=score.total,
        comment=score.comment,
        details=score.model_dump(by_alias=True),
        provider=None if score.eliminated else provider,
        model=None if score.eliminated else model,
    )
    return score
