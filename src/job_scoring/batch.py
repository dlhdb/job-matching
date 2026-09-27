"""整批評分：依輸入順序逐筆評分，單筆失敗不中斷。送去評分與試跑都走這裡。"""

import sqlite3
from typing import Any, Callable

from pydantic import ValidationError

from job_scoring.llm import LLMClient, LLMError
from job_scoring.models import BatchResult
from job_scoring.rules import check_hard_filters
from job_scoring.scorer import score_and_save
from job_scoring.settings import ScoringSettings


def score_batch(
    jobs: list[dict[str, Any]],
    settings: ScoringSettings,
    client_factory: Callable[[], LLMClient],
    *,
    conn: sqlite3.Connection | None,
    provider: str,
    model: str,
    should_stop: Callable[[], bool] = lambda: False,
    on_start: Callable[[int, dict[str, Any]], None] = lambda i, job: None,
    on_result: Callable[[int, BatchResult], None] = lambda i, result: None,
) -> list[BatchResult]:
    """
    依輸入順序逐筆評分，每筆評完就寫入 job_scores；LLM 呼叫失敗或回應驗證失敗時記下原因並繼續下一筆（不寫入）。
    conn 為 None 時是試跑：只評分，不寫入資料庫。

    有需要呼叫 AI 的職缺時，開始評分前就建立 client：建立失敗（例如缺少 API key）時每一筆都會失敗，
    所以直接往外拋，這時還沒有寫入任何一筆。

    :param jobs: list[dict], 符合職缺欄位契約的職缺
    :param settings: ScoringSettings, 評分用的設定，整批都用同一組
    :param client_factory: callable, 建立 LLM client；整批都被淘汰時不呼叫
    :param conn: sqlite3.Connection or None, open_db 開啟的連線，評分結果寫入其中的 job_scores；None 表示試跑
    :param provider: str, client_factory 使用的 LLM 供應商
    :param model: str, client_factory 使用的模型名稱
    :param should_stop: callable, 每筆開始前呼叫，回傳 True 時不再評之後的職缺
    :param on_start: callable, on_start(index, job)，每筆開始前呼叫；index 從 0 起算
    :param on_result: callable, on_result(index, result)，每筆評完（含失敗）後呼叫
    :return: list[BatchResult], 與輸入順序相同，只含有評的職缺；停止時比輸入少
    :raises ValueError: client_factory 不認得供應商
    :raises LLMError: client_factory 建立 client 失敗（例如缺少 API key）
    :raises sqlite3.Error: 寫入資料庫失敗；已寫入的職缺留在資料庫中
    """
    needs_ai = any(not check_hard_filters(job, settings.preferences) for job in jobs)
    client = client_factory() if needs_ai else None

    results = []
    for i, job in enumerate(jobs):
        if should_stop():
            break
        on_start(i, job)
        job_no = str(job.get("職缺代碼") or "")
        try:
            score = score_and_save(job, settings, client, conn, provider, model)
        except (LLMError, ValidationError) as e:
            result = BatchResult(
                job_no=job_no, eliminated=False, elimination_reasons=[], dimensions=None,
                total=None, unknown_dimensions=[], comment=None, failure=str(e),
            )
        else:
            result = BatchResult(
                job_no=job_no,
                eliminated=score.eliminated,
                elimination_reasons=score.elimination_reasons,
                dimensions=score.dimensions,
                total=score.total,
                unknown_dimensions=score.unknown_dimensions,
                comment=score.comment,
                failure=None,
            )
        results.append(result)
        on_result(i, result)
    return results
