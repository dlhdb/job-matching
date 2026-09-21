"""讀寫評分結果（job_scores）。"""

import json
import sqlite3
from datetime import datetime
from typing import Any

from job_db._sql import limit_clause, rows_to_dicts
from job_db.schema import JOB_COLUMNS

# 列表要從 jobs 帶的職缺欄位；職缺代碼改從 job_scores 取，沒匯入職缺資料的職缺才不會連代碼都是 None
_JOINED_JOB_FIELDS = [name for name, _ in JOB_COLUMNS if name != "職缺代碼"]

# 列表要帶的評分欄位，不含完整評分結果與快取鍵
_SCORE_FIELDS = ["評分時間", "淘汰", "總分", "評語", "供應商", "模型"]


def save_score(
    conn: sqlite3.Connection,
    *,
    job_no: str,
    scored_at: datetime,
    eliminated: bool,
    total: int | None,
    comment: str | None,
    result: dict[str, Any],
    cache_key: str | None,
    provider: str | None,
    model: str | None,
) -> None:
    """
    寫入一筆職缺的評分結果；同一個職缺代碼已有列時整列覆寫。單筆自成一個交易。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :param scored_at: datetime, 評分時間（本地時間）
    :param eliminated: bool, 是否被硬性淘汰
    :param total: int or None, 總分；被淘汰時為 None
    :param comment: str or None, AI 的總評；被淘汰時為 None
    :param result: dict, 中文鍵名的完整評分結果，以 JSON 存入
    :param cache_key: str or None, 快取鍵；被淘汰時為 None
    :param provider: str or None, LLM 供應商；被淘汰時為 None
    :param model: str or None, 模型名稱；被淘汰時為 None
    """
    with conn:
        conn.execute(
            'INSERT INTO job_scores ("職缺代碼", "評分時間", "淘汰", "總分", "評語", "評分結果", "快取鍵", "供應商", "模型") '
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            'ON CONFLICT ("職缺代碼") DO UPDATE SET '
            '"評分時間" = excluded."評分時間", "淘汰" = excluded."淘汰", "總分" = excluded."總分", '
            '"評語" = excluded."評語", "評分結果" = excluded."評分結果", "快取鍵" = excluded."快取鍵", '
            '"供應商" = excluded."供應商", "模型" = excluded."模型"',
            (
                job_no,
                scored_at.isoformat(timespec="seconds"),
                int(eliminated),
                total,
                comment,
                json.dumps(result, ensure_ascii=False),
                cache_key,
                provider,
                model,
            ),
        )


def load_cached_result(conn: sqlite3.Connection, job_no: str, cache_key: str) -> dict[str, Any] | None:
    """
    取出快取鍵相同的上次評分結果；被淘汰的列沒有快取鍵，不會被取出。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :param cache_key: str, 這次評分的快取鍵
    :return: dict or None, 中文鍵名的完整評分結果；沒有評過或快取鍵不同時為 None
    """
    row = conn.execute(
        'SELECT "評分結果" FROM job_scores WHERE "職缺代碼" = ? AND "快取鍵" = ?', (job_no, cache_key),
    ).fetchone()
    return None if row is None else json.loads(row[0])


def list_scored_jobs(
    conn: sqlite3.Connection,
    *,
    eliminated: bool | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """
    列出評過分的職缺，排序為總分由高到低，被淘汰的職缺沒有總分、排在最後。

    評分時不必先把職缺匯入資料庫，所以查到只有評分、沒有職缺資料的職缺時，職缺欄位為 None。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param eliminated: bool or None, True 只列被淘汰的、False 只列沒被淘汰的；None 代表不限
    :param limit: int or None, 最多取幾筆；None 代表不限
    :param offset: int or None, 從第幾筆開始；None 代表從頭
    :return: list[dict], 每筆是職缺欄位加上評分時間、淘汰、總分、評語、供應商、模型
    :raises ValueError: limit 或 offset 是負數
    """
    columns = ", ".join(
        ['job_scores."職缺代碼"']
        + [f'jobs."{name}"' for name in _JOINED_JOB_FIELDS]
        + [f'job_scores."{name}"' for name in _SCORE_FIELDS]
    )
    params: list[Any] = []
    where = ""
    if eliminated is not None:
        where = 'WHERE job_scores."淘汰" = ? '
        params.append(int(eliminated))
    # 總分相同（含淘汰時的 NULL）再比職缺代碼，同樣的資料每次查出來的順序才一致
    sql = (
        f"SELECT {columns} FROM job_scores "
        'LEFT JOIN jobs ON jobs."職缺代碼" = job_scores."職缺代碼" '
        f"{where}"
        'ORDER BY job_scores."總分" IS NULL, job_scores."總分" DESC, job_scores."職缺代碼"'
    )
    clause, extra = limit_clause(limit, offset)
    return rows_to_dicts(conn.execute(sql + clause, params + extra))


def get_score(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    取出單筆職缺的完整評分結果，含各維度的分數與理由。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 中文鍵名的完整評分結果；沒有評過這筆職缺時為 None
    """
    row = conn.execute(
        'SELECT "評分結果" FROM job_scores WHERE "職缺代碼" = ?', (job_no,),
    ).fetchone()
    return None if row is None else json.loads(row[0])
