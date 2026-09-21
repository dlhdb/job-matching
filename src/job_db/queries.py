"""依條件查出職缺欄位契約的職缺，以及每次寫入的執行紀錄。"""

import sqlite3
from typing import Any

from job_db._sql import limit_clause, rows_to_dicts
from job_db.schema import JOB_COLUMNS

# 職缺欄位契約的欄位，加上寫入時記下的出現時間；順序與資料表相同
_JOB_FIELDS = [name for name, _ in JOB_COLUMNS] + ["首次出現時間", "最後出現時間"]

# 最後出現時間相同時再比職缺代碼，同樣的資料每次查出來的順序才一致
_JOB_ORDER = 'ORDER BY jobs."最後出現時間" DESC, jobs."職缺代碼"'


def list_jobs(
    conn: sqlite3.Connection,
    *,
    run_id: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """
    依條件列出職缺，排序為最後出現時間由新到舊。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param run_id: int or None, 只列出這次寫入出現的職缺；None 代表不限
    :param limit: int or None, 最多取幾筆；None 代表不限
    :param offset: int or None, 從第幾筆開始；None 代表從頭
    :return: list[dict], 每筆是職缺欄位契約的欄位加上首次、最後出現時間；沒有符合的為空清單
    :raises ValueError: limit 或 offset 是負數
    """
    columns = ", ".join(f'jobs."{name}"' for name in _JOB_FIELDS)
    params: list[Any] = []
    if run_id is None:
        sql = f"SELECT {columns} FROM jobs {_JOB_ORDER}"
    else:
        sql = (
            f"SELECT {columns} FROM jobs "
            'JOIN run_jobs ON run_jobs."職缺代碼" = jobs."職缺代碼" '
            'WHERE run_jobs."執行編號" = ? '
            f"{_JOB_ORDER}"
        )
        params.append(run_id)
    clause, extra = limit_clause(limit, offset)
    return rows_to_dicts(conn.execute(sql + clause, params + extra))


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
