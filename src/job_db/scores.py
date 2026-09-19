"""讀寫評分結果（job_scores）。"""

import json
import sqlite3
from datetime import datetime
from typing import Any


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
