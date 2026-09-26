"""查出職缺欄位契約的職缺、哪些職缺代碼已經在資料庫裡，以及每次寫入的執行紀錄。"""

import json
import sqlite3
from typing import Any

from job_db._sql import limit_clause, rows_to_dicts
from job_db.schema import JOB_COLUMNS

# 職缺欄位契約的欄位，加上寫入時記下的出現時間；順序與資料表相同
_JOB_FIELDS = [name for name, _ in JOB_COLUMNS] + ["首次出現時間", "最後出現時間"]

# 最後出現時間相同時再比職缺代碼，同樣的資料每次查出來的順序才一致
_JOB_ORDER = 'ORDER BY "最後出現時間" DESC, "職缺代碼"'


def list_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    列出全部職缺，排序為最後出現時間由新到舊。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: list[dict], 每筆是職缺欄位契約的欄位加上首次、最後出現時間；沒有職缺時為空清單
    """
    columns = ", ".join(f'"{name}"' for name in _JOB_FIELDS)
    return rows_to_dicts(conn.execute(f"SELECT {columns} FROM jobs {_JOB_ORDER}"))


def get_job(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    以職缺代碼取出單筆職缺的完整內容。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 欄位同 list_jobs 的單筆；沒有這筆職缺時為 None
    """
    columns = ", ".join(f'"{name}"' for name in _JOB_FIELDS)
    rows = rows_to_dicts(
        conn.execute(f'SELECT {columns} FROM jobs WHERE "職缺代碼" = ?', (job_no,))
    )
    return rows[0] if rows else None


def existing_job_codes(conn: sqlite3.Connection, codes: list[str]) -> set[str]:
    """
    從一批職缺代碼中找出資料庫裡已經有的。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param codes: list[str], 要檢查的職缺代碼
    :return: set[str], 其中已經在資料庫裡的職缺代碼
    """
    if not codes:
        return set()
    # 用 JSON 陣列一次帶入，不受 SQLite 單一語句參數個數的上限影響
    rows = conn.execute(
        'SELECT "職缺代碼" FROM jobs WHERE "職缺代碼" IN (SELECT value FROM json_each(?))',
        (json.dumps(codes),),
    )
    return {row[0] for row in rows}


def list_runs(conn: sqlite3.Connection, *, limit: int | None = None) -> list[dict[str, Any]]:
    """
    列出每次寫入的執行紀錄，排序為執行時間由新到舊。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param limit: int or None, 最多取幾筆；None 代表不限
    :return: list[dict], 每筆是一次寫入的執行紀錄；沒有紀錄時為空清單
    :raises ValueError: limit 是負數
    """
    sql = 'SELECT * FROM scrape_runs ORDER BY "執行時間" DESC, "執行編號" DESC'
    clause, params = limit_clause(limit, None)
    return rows_to_dicts(conn.execute(sql + clause, params))
