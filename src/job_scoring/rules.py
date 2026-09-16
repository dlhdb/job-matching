"""程式規則：硬性淘汰（job-scoring.md §4）與薪資換算、計分（§5）。"""

from typing import Any, NamedTuple

from job_scoring.models import Preferences

# 104 以此值代表「以上」（沒有上限）
NO_UPPER_BOUND = 9999999


class MonthlyRange(NamedTuple):
    """換算成月薪後的薪資區間"""

    kind: str          # 原始薪資類型：月薪或年薪
    raw_low: int       # 原始下限
    raw_high: int | None
    low: int           # 換算後的月薪下限
    high: int | None   # 換算後的月薪上限；None 代表沒有上限


def _monthly_range(job: dict[str, Any], prefs: Preferences) -> MonthlyRange | None:
    """
    依薪資待遇的開頭判斷類型，換算成月薪區間；無法換算時回傳 None（薪資未知）。

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定（使用年薪換算月數）
    :return: MonthlyRange or None, 月薪區間；面議、時薪、日薪、論件計酬、缺值都回傳 None
    """
    salary_text = job.get("薪資待遇")
    raw_low = job.get("薪資下限")
    raw_high = job.get("薪資上限")
    if not isinstance(salary_text, str) or not raw_low:
        return None
    if raw_high is not None and raw_high >= NO_UPPER_BOUND:
        raw_high = None

    if salary_text.startswith("月薪"):
        return MonthlyRange("月薪", raw_low, raw_high, raw_low, raw_high)
    if salary_text.startswith("年薪"):
        months = prefs.salary.annual_months
        high = round(raw_high / months) if raw_high is not None else None
        return MonthlyRange("年薪", raw_low, raw_high, round(raw_low / months), high)
    return None


def _format_range(low: int, high: int | None) -> str:
    """
    把薪資區間格式化成顯示用字串，例如「60,000–80,000」或「50,000 以上」

    :param low: int, 下限
    :param high: int or None, 上限；None 代表沒有上限
    :return: str, 顯示用字串
    """
    return f"{low:,} 以上" if high is None else f"{low:,}–{high:,}"


def check_hard_filters(job: dict[str, Any], prefs: Preferences) -> list[str]:
    """
    依序檢查所有硬性淘汰條件，收集全部符合的原因（不在第一條停止）。

    :param job: dict, 爬蟲輸出的單筆職缺
    :param prefs: Preferences, 偏好設定
    :return: list[str], 淘汰原因；空清單代表沒被淘汰
    """
    reasons = []
    company = job.get("公司名稱")
    if company and company in prefs.elimination.companies:
        reasons.append(f"公司在排除名單：{company}")

    title = (job.get("職缺名稱") or "").casefold()
    for keyword in prefs.elimination.title_keywords:
        if keyword.casefold() in title:
            reasons.append(f"職稱含排除關鍵字：{keyword}")

    monthly = _monthly_range(job, prefs)
    floor = prefs.salary.minimum
    if monthly and monthly.high is not None and monthly.high < floor:
        reasons.append(f"薪資上限 {monthly.high:,} 低於底線 {floor:,}")
    return reasons


def score_salary(job: dict[str, Any], prefs: Preferences) -> tuple[int | None, str]:
    """
    依換算後的月薪區間計算薪資水準分數；薪資未知時分數為 None。

    :param job: dict, 爬蟲輸出的單筆職缺（假設已通過硬性淘汰）
    :param prefs: Preferences, 偏好設定
    :return: tuple (int or None, str), (分數, 理由)
    """
    monthly = _monthly_range(job, prefs)
    if monthly is None:
        salary_text = job.get("薪資待遇") or "無資料"
        return None, f"薪資未知（{salary_text}），無法換算月薪"

    expected = prefs.salary.expected
    if monthly.low >= expected:
        score, verdict = 5, "下限已達期望"
    elif monthly.high is not None and monthly.high >= expected:
        score, verdict = 4, "區間涵蓋期望"
    else:
        score, verdict = 2, "未達期望"

    described = f"{monthly.kind} {_format_range(monthly.raw_low, monthly.raw_high)}"
    if monthly.kind == "年薪":
        described += f"（換算月薪 {_format_range(monthly.low, monthly.high)}）"
    return score, f"{described}，期望 {expected:,}，{verdict}"
