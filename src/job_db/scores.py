"""讀寫評分紀錄（job_scores）：評分紀錄的基本欄位，以及自動評分疊加的欄位。

同一筆職缺可以有多筆評分紀錄：自動與手動評分每次都新增一筆，不覆寫任何紀錄。
依分數列出、取出單筆評分紀錄與評分明細時，每筆職缺只用一筆代表的評分：最新的一筆，不分自動或手動。
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

# 取出單筆評分紀錄要帶的評分欄位：基本欄位加上評分來源
_CURRENT_FIELDS = _RECORD_FIELDS + ["評分來源"]

# 列表要帶的評分欄位：再加上自動評分的供應商、模型，不含評分明細
_SCORE_FIELDS = _CURRENT_FIELDS + ["供應商", "模型"]

# 取出一筆職缺所有評分紀錄時的欄位
_HISTORY_FIELDS = ["職缺代碼"] + _SCORE_FIELDS + ["評分明細"]

# 自動評分寫入的欄位（評分時間以外）
_AUTO_FIELDS = ["淘汰", "總分", "評語", "評分明細", "供應商", "模型"]

# 列出還沒評分的職缺時帶的欄位：職缺欄位契約加上出現時間，與 get_job 相同
_UNSCORED_JOB_FIELDS = [name for name, _ in JOB_COLUMNS] + ["首次出現時間", "最後出現時間"]

# 同一筆職缺的多筆紀錄由新到舊；評分時間只精確到秒，同一秒內的再以評分編號區分先後
_LATEST_FIRST = 'ORDER BY "評分時間" DESC, "評分編號" DESC'

# 每筆職缺代表的評分：最新的一筆，不分自動或手動
_CURRENT = (
    "(SELECT * FROM ("
    f'SELECT *, ROW_NUMBER() OVER (PARTITION BY "職缺代碼" {_LATEST_FIRST}) AS _rank '
    "FROM job_scores) WHERE _rank = 1)"
)


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
    新增一筆手動評分，評分時間為寫入當下；不覆寫任何紀錄，查詢時以最新的一筆為準。單筆自成一個交易。

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
            'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", "淘汰", "總分", "評語") '
            "VALUES (?, 'manual', ?, ?, ?, ?)",
            (job_no, datetime.now().isoformat(timespec="seconds"), int(eliminated), total, comment),
        )


def get_score(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    取出單筆職缺代表的評分紀錄：最新的一筆，不分自動或手動

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 職缺代碼、評分時間、淘汰、總分、評語、評分來源；沒有評過這筆職缺時為 None
    """
    columns = ", ".join(f'"{name}"' for name in ["職缺代碼"] + _CURRENT_FIELDS)
    rows = rows_to_dicts(conn.execute(
        f'SELECT {columns} FROM {_CURRENT} WHERE "職缺代碼" = ?', (job_no,),
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
    provider: str | None,
    model: str | None,
) -> None:
    """
    新增一筆自動評分，不覆寫任何紀錄，也不和先前的紀錄比較。單筆自成一個交易。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :param scored_at: datetime, 評分時間（本地時間）
    :param eliminated: bool, 是否被硬性淘汰
    :param total: int or None, 總分；被淘汰時為 None
    :param comment: str, 評語：AI 的總評，被淘汰時為淘汰原因組成的文字
    :param details: dict, 中文鍵名的評分明細（完整評分結果），以 JSON 存入
    :param provider: str or None, LLM 供應商；被淘汰時為 None
    :param model: str or None, 模型名稱；被淘汰時為 None
    """
    values = (int(eliminated), total, comment, json.dumps(details, ensure_ascii=False), provider, model)
    columns = ", ".join(f'"{name}"' for name in _AUTO_FIELDS)
    placeholders = ", ".join("?" * len(values))
    with conn:
        conn.execute(
            f'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", {columns}) '
            f"VALUES (?, 'auto', ?, {placeholders})",
            (job_no, scored_at.isoformat(timespec="seconds"), *values),
        )


def list_unscored_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    列出還沒有任何評分紀錄（自動或手動）的職缺，排序為最後出現時間由新到舊，相同時再比職缺代碼。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: list[dict], 每筆是職缺欄位契約的欄位加上首次、最後出現時間；沒有時為空清單
    """
    columns = ", ".join(f'jobs."{name}"' for name in _UNSCORED_JOB_FIELDS)
    return rows_to_dicts(conn.execute(
        f"SELECT {columns} FROM jobs "
        'WHERE NOT EXISTS (SELECT 1 FROM job_scores s WHERE s."職缺代碼" = jobs."職缺代碼") '
        'ORDER BY jobs."最後出現時間" DESC, jobs."職缺代碼"'
    ))


def list_scored_jobs(
    conn: sqlite3.Connection,
    *,
    eliminated: bool | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """
    列出評過分的職缺，排序為總分由高到低，沒有總分的排在最後；每筆職缺只列代表的評分一次。

    評分時不必先把職缺匯入資料庫，所以查到只有評分、沒有職缺資料的職缺時，職缺欄位為 None。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param eliminated: bool or None, 依代表的評分篩選：True 只列被淘汰的、False 只列沒被淘汰的；None 代表不限
    :param limit: int or None, 最多取幾筆；None 代表不限
    :param offset: int or None, 從第幾筆開始；None 代表從頭
    :return: list[dict], 每筆是職缺欄位加上評分時間、淘汰、總分、評語、評分來源、供應商、模型
    :raises ValueError: limit 或 offset 是負數
    """
    columns = ", ".join(
        ['s."職缺代碼"']
        + [f'jobs."{name}"' for name in _JOINED_JOB_FIELDS]
        + [f's."{name}"' for name in _SCORE_FIELDS]
    )
    params: list[Any] = []
    where = ""
    # 先挑出代表的評分再篩選，淘汰與否以代表的那筆為準
    if eliminated is not None:
        where = 'WHERE s."淘汰" = ? '
        params.append(int(eliminated))
    # 總分相同（含沒有總分的 NULL）再比職缺代碼，同樣的資料每次查出來的順序才一致
    sql = (
        f"SELECT {columns} FROM {_CURRENT} AS s "
        'LEFT JOIN jobs ON jobs."職缺代碼" = s."職缺代碼" '
        f"{where}"
        'ORDER BY s."總分" IS NULL, s."總分" DESC, s."職缺代碼"'
    )
    clause, extra = limit_clause(limit, offset)
    return rows_to_dicts(conn.execute(sql + clause, params + extra))


def get_score_details(conn: sqlite3.Connection, job_no: str) -> dict[str, Any] | None:
    """
    取出單筆職缺代表的評分的評分明細，含各維度的分數與理由。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: dict or None, 中文鍵名的評分明細；沒有評過這筆職缺，或代表的評分是手動評分時為 None
    """
    row = conn.execute(
        f'SELECT "評分來源", "評分明細" FROM {_CURRENT} WHERE "職缺代碼" = ?', (job_no,),
    ).fetchone()
    if row is None or row[0] != "auto":
        return None
    return json.loads(row[1])


def list_scores(conn: sqlite3.Connection, job_no: str) -> list[dict[str, Any]]:
    """
    取出單筆職缺的所有評分紀錄，依評分時間由新到舊（同一秒內後寫入的在前），手動與自動都列出。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: list[dict], 每筆是職缺代碼、評分時間、淘汰、總分、評語、評分來源、供應商、模型、評分明細（中文鍵名的 dict，
        手動評分為 None）；沒有評過這筆職缺時為空清單
    """
    columns = ", ".join(f'"{name}"' for name in _HISTORY_FIELDS)
    rows = rows_to_dicts(conn.execute(
        f'SELECT {columns} FROM job_scores WHERE "職缺代碼" = ? {_LATEST_FIRST}', (job_no,),
    ))
    for row in rows:
        if row["評分明細"] is not None:
            row["評分明細"] = json.loads(row["評分明細"])
    return rows
