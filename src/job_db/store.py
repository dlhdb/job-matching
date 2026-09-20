"""把一批符合職缺欄位契約的職缺寫入資料庫。"""

import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from job_db.schema import JOB_COLUMNS

# 新資料為 null 時保留舊值的欄位：詳情 API 暫時失敗時這兩欄為 null，不該蓋掉先前抓到的內容
_KEEP_ON_NULL = {"工作內容", "薪資待遇"}

_COLUMN_NAMES = [name for name, _ in JOB_COLUMNS]


@dataclass
class SaveResult:
    """一次寫入的結果"""

    inserted: int
    updated: int


def _quote(name: str) -> str:
    return f'"{name}"'


def _upsert_job(conn: sqlite3.Connection, job: dict[str, Any], t: str) -> bool:
    """
    依出現時間寫入單筆職缺

    :param conn: sqlite3.Connection, 已開啟的連線（呼叫端負責交易）
    :param job: dict, 符合職缺欄位契約的單筆職缺
    :param t: str, 本次執行時間（ISO 8601）
    :return: bool, True 代表新增，False 代表更新
    """
    job_no = job.get("職缺代碼")
    row = conn.execute(
        'SELECT "首次出現時間", "最後出現時間" FROM jobs WHERE "職缺代碼" = ?', (job_no,)
    ).fetchone()
    values = [job.get(name) for name in _COLUMN_NAMES]

    if row is None:
        columns = [*_COLUMN_NAMES, "首次出現時間", "最後出現時間"]
        placeholders = ", ".join("?" * len(columns))
        conn.execute(
            f"INSERT INTO jobs ({', '.join(map(_quote, columns))}) VALUES ({placeholders})",
            [*values, t, t],
        )
        return True

    first_seen, last_seen = row
    first_seen = min(first_seen, t)
    if t >= last_seen:
        # 只有不早於最後出現時間的資料才覆蓋欄位，匯入舊檔的先後順序才不影響結果
        assignments = [
            f"{_quote(name)} = COALESCE(?, {_quote(name)})" if name in _KEEP_ON_NULL else f"{_quote(name)} = ?"
            for name in _COLUMN_NAMES[1:]
        ]
        assignments += ['"首次出現時間" = ?', '"最後出現時間" = ?']
        conn.execute(
            f'UPDATE jobs SET {", ".join(assignments)} WHERE "職缺代碼" = ?',
            [*values[1:], first_seen, t, job_no],
        )
    else:
        conn.execute('UPDATE jobs SET "首次出現時間" = ? WHERE "職缺代碼" = ?', (first_seen, job_no))
    return False


def _db_path(conn: sqlite3.Connection) -> str:
    """
    取得連線對應的資料庫檔路徑

    :param conn: sqlite3.Connection, 已開啟的連線
    :return: str, 資料庫檔路徑
    """
    for _, name, file in conn.execute("PRAGMA database_list"):
        if name == "main":
            return str(file)
    return ""


def save_run(
    conn: sqlite3.Connection,
    jobs: list[dict[str, Any]],
    run_time: datetime,
    source: str,
    *,
    keywords: str | None = None,
    area: str | None = None,
    job_type: int | None = None,
    pages: int | None = None,
    source_file: str | None = None,
) -> SaveResult:
    """
    把一次抓取或匯入的職缺寫入資料庫，並記錄這次執行；整批在同一個交易中，失敗時全部 rollback。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param jobs: list[dict], 符合職缺欄位契約的職缺
    :param run_time: datetime, 本次執行時間（本地時間）
    :param source: str, "爬蟲" 或 "匯入"
    :param keywords: str or None, 以 ", " 合併的關鍵字
    :param area: str or None, 縣市名稱或「全台灣」
    :param job_type: int or None, 職缺性質 0／1／2
    :param pages: int or None, 每個關鍵字抓取的頁數
    :param source_file: str or None, 匯入的 JSON 檔名（不含目錄）
    :return: SaveResult, 新增與更新的筆數
    """
    t = run_time.isoformat(timespec="seconds")
    inserted = updated = 0
    with conn:
        cursor = conn.execute(
            'INSERT INTO scrape_runs ("執行時間", "來源", "關鍵字", "地區", "職缺性質", "頁數", "來源檔", "職缺數") '
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (t, source, keywords, area, job_type, pages, source_file),
        )
        run_id = cursor.lastrowid
        seen: set[Any] = set()
        for job in jobs:
            if _upsert_job(conn, job, t):
                inserted += 1
            else:
                updated += 1
            seen.add(job.get("職缺代碼"))
            conn.execute(
                'INSERT OR IGNORE INTO run_jobs ("執行編號", "職缺代碼") VALUES (?, ?)',
                (run_id, job.get("職缺代碼")),
            )
        conn.execute('UPDATE scrape_runs SET "職缺數" = ? WHERE "執行編號" = ?', (len(seen), run_id))

    print(f"[+] 已寫入資料庫：新增 {inserted} 筆、更新 {updated} 筆（{_db_path(conn)}）", file=sys.stderr)
    return SaveResult(inserted, updated)
