"""讀寫評分紀錄（job_scores）：評分紀錄的基本欄位，以及自動評分疊加的欄位。

同一筆職缺可以有多筆評分紀錄：自動評分每次有變化就新增一筆，手動評分每筆職缺最多一筆。
"""

import json
import sqlite3
from datetime import datetime
from typing import Any

from job_db._sql import limit_clause, rows_to_dicts
from job_db.schema import JOB_COLUMNS

# 列表要從 jobs 帶的職缺欄位；職缺代碼改從 job_scores 取，沒匯入職缺資料的職缺才不會連代碼都是 None
_JOINED_JOB_FIELDS = [name for name, _ in JOB_COLUMNS if name != "職缺代碼"]

# 評分紀錄的基本欄位（不含職缺代碼）
_RECORD_FIELDS = ["評分時間", "淘汰", "總分", "評語"]

# 列表要帶的評分欄位：基本欄位加上自動評分的供應商、模型，不含評分明細與快取鍵
_SCORE_FIELDS = _RECORD_FIELDS + ["供應商", "模型"]

# 自動評分判斷有沒有變化時比較的欄位：評分時間以外的全部欄位
_AUTO_FIELDS = ["淘汰", "總分", "評語", "評分明細", "快取鍵", "供應商", "模型"]

# 同一筆職缺的多筆紀錄由新到舊；評分時間只精確到秒，同一秒內的再以評分編號區分先後
_LATEST_FIRST = 'ORDER BY "評分時間" DESC, "評分編號" DESC'


def _check_manual_score(job_no: str, comment: str | None, total: int | None) -> None:
    """
    檢查手動評分的欄位

    :param job_no: str, 職缺代碼
    :param comment: str or None, 評語
    :param total: int or None, 總分
    :raises ValueError: 職缺代碼或評語缺少或為空、總分不是 0–100 的整數
    """
    if not isinstance(job_no, str) or not job_no.strip():
        raise ValueError(f"職缺代碼必填，不可為空：{job_no!r}")
    if not isinstance(comment, str) or not comment.strip():
        raise ValueError(f"評語必填，不可為空：{comment!r}")
    # bool 是 int 的子類別，要另外排除
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 100):
        raise ValueError(f"總分必須是 0–100 的整數：{total!r}")


def save_score(
    conn: sqlite3.Connection,
    *,
    job_no: str,
    comment: str | None,
    total: int | None = None,
    eliminated: bool = False,
) -> None:
    """
    寫入一筆手動評分，評分時間為寫入當下；只覆寫同一筆職缺上一次的手動評分，不動自動評分。單筆自成一個交易。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼，必填
    :param comment: str or None, 評語，必填且不可為空
    :param total: int or None, 總分，0–100；None 代表沒有總分
    :param eliminated: bool, 是否淘汰，預設為否
    :raises ValueError: 欄位不符合時拋出，資料庫不變
    """
    _check_manual_score(job_no, comment, total)
    with conn:
        conn.execute(
            'DELETE FROM job_scores WHERE "職缺代碼" = ? AND "評分來源" = \'manual\'', (job_no,),
        )
        conn.execute(
            'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", "淘汰", "總分", "評語") '
            "VALUES (?, 'manual', ?, ?, ?, ?)",
            (job_no, datetime.now().isoformat(timespec="seconds"), int(eliminated), total, comment),
        )


def get_score(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    取出單筆職缺的評分紀錄；有多筆時取評分時間最新的一筆，不分手動或自動

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 職缺代碼、評分時間、淘汰、總分、評語；沒有評過這筆職缺時為 None
    """
    columns = ", ".join(f'"{name}"' for name in ["職缺代碼"] + _RECORD_FIELDS)
    rows = rows_to_dicts(conn.execute(
        f'SELECT {columns} FROM job_scores WHERE "職缺代碼" = ? {_LATEST_FIRST} LIMIT 1', (job_no,),
    ))
    return rows[0] if rows else None


def save_auto_score(
    conn: sqlite3.Connection,
    *,
    job_no: str,
    scored_at: datetime,
    eliminated: bool,
    total: int | None,
    comment: str,
    details: dict[str, Any],
    cache_key: str | None,
    provider: str | None,
    model: str | None,
) -> bool:
    """
    新增一筆自動評分，不覆寫任何紀錄；與這筆職缺最新一筆自動評分除了評分時間都相同時不新增。單筆自成一個交易。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :param scored_at: datetime, 評分時間（本地時間）
    :param eliminated: bool, 是否被硬性淘汰
    :param total: int or None, 總分；被淘汰時為 None
    :param comment: str, 評語：AI 的總評，被淘汰時為淘汰原因組成的文字
    :param details: dict, 中文鍵名的評分明細（完整評分結果），以 JSON 存入
    :param cache_key: str or None, 快取鍵；被淘汰時為 None
    :param provider: str or None, LLM 供應商；被淘汰時為 None
    :param model: str or None, 模型名稱；被淘汰時為 None
    :return: bool, 是否新增了一筆
    """
    values = (int(eliminated), total, comment, json.dumps(details, ensure_ascii=False), cache_key, provider, model)
    columns = ", ".join(f'"{name}"' for name in _AUTO_FIELDS)
    with conn:
        latest = conn.execute(
            f'SELECT {columns} FROM job_scores WHERE "職缺代碼" = ? AND "評分來源" = \'auto\' {_LATEST_FIRST} LIMIT 1',
            (job_no,),
        ).fetchone()
        if latest == values:
            return False
        conn.execute(
            f'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", {columns}) '
            "VALUES (?, 'auto', ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_no, scored_at.isoformat(timespec="seconds"), *values),
        )
    return True


def load_cached_result(conn: sqlite3.Connection, job_no: str, cache_key: str) -> dict[str, Any] | None:
    """
    從這筆職缺的所有自動評分中，取出快取鍵相同的最新一筆評分明細；被淘汰的紀錄沒有快取鍵，不會被取出。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :param cache_key: str, 這次評分的快取鍵
    :return: dict or None, 中文鍵名的評分明細；沒有評過或快取鍵都不同時為 None
    """
    row = conn.execute(
        'SELECT "評分明細" FROM job_scores '
        f'WHERE "職缺代碼" = ? AND "評分來源" = \'auto\' AND "快取鍵" = ? {_LATEST_FIRST} LIMIT 1',
        (job_no, cache_key),
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
    列出評過分的職缺，排序為總分由高到低，沒有總分的排在最後；每筆評分紀錄各一列，同一筆職缺可能出現多次。

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
    # 總分相同（含沒有總分的 NULL）再比職缺代碼，同樣的資料每次查出來的順序才一致
    sql = (
        f"SELECT {columns} FROM job_scores "
        'LEFT JOIN jobs ON jobs."職缺代碼" = job_scores."職缺代碼" '
        f"{where}"
        'ORDER BY job_scores."總分" IS NULL, job_scores."總分" DESC, job_scores."職缺代碼"'
    )
    clause, extra = limit_clause(limit, offset)
    return rows_to_dicts(conn.execute(sql + clause, params + extra))


def get_score_details(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    取出單筆職缺最新一筆自動評分的評分明細，含各維度的分數與理由。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 中文鍵名的評分明細；沒有評過這筆職缺，或只有手動評分時為 None
    """
    row = conn.execute(
        f'SELECT "評分明細" FROM job_scores WHERE "職缺代碼" = ? AND "評分來源" = \'auto\' {_LATEST_FIRST} LIMIT 1',
        (job_no,),
    ).fetchone()
    return None if row is None else json.loads(row[0])
