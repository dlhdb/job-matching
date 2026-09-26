"""讀寫評分紀錄（job_scores）。

同一筆職缺可以有多筆評分紀錄：每次評分都新增一筆，不覆寫任何紀錄。
列出各職缺的評分時，每筆職缺只用一筆代表的評分：最新的一筆。
"""

import json
import sqlite3
from datetime import datetime
from typing import Any

from job_db._sql import rows_to_dicts

# 評分紀錄的欄位，不含職缺代碼、評分明細與評分依據
_SCORE_FIELDS = ["評分時間", "淘汰", "總分", "評語", "供應商", "模型"]

# 評分依據：評分時用的三份設定的版本，與送評時的職缺內容快照；記錄依據之前的評分都是 NULL
_BASIS_FIELDS = ["偏好版本", "經歷版本", "模板版本", "職缺快照"]

# 取出一筆職缺所有評分紀錄時的欄位
_HISTORY_FIELDS = ["職缺代碼"] + _SCORE_FIELDS + ["評分明細"] + _BASIS_FIELDS

# 同一筆職缺的多筆紀錄由新到舊；評分時間只精確到秒，同一秒內的再以評分編號區分先後
_LATEST_FIRST = 'ORDER BY "評分時間" DESC, "評分編號" DESC'

# 每筆職缺代表的評分：最新的一筆
_CURRENT = (
    "(SELECT * FROM ("
    f'SELECT *, ROW_NUMBER() OVER (PARTITION BY "職缺代碼" {_LATEST_FIRST}) AS _rank '
    "FROM job_scores) WHERE _rank = 1)"
)


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
    basis: dict[str, Any],
) -> None:
    """
    新增一筆評分紀錄，不覆寫任何紀錄，也不和先前的紀錄比較。單筆自成一個交易。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼，必須已在 jobs 中
    :param scored_at: datetime, 評分時間（本地時間）
    :param eliminated: bool, 是否被硬性淘汰
    :param total: int or None, 總分；被淘汰時為 None
    :param comment: str, 評語：AI 的總評，被淘汰時為淘汰原因組成的文字
    :param details: dict, 中文鍵名的評分明細（完整評分結果），以 JSON 存入
    :param provider: str or None, LLM 供應商；被淘汰時為 None
    :param model: str or None, 模型名稱；被淘汰時為 None
    :param basis: dict, 評分依據：偏好版本、經歷版本、模板版本（int）與職缺快照（dict，以 JSON 存入）
    :raises sqlite3.IntegrityError: jobs 中沒有這筆職缺
    """
    values = (
        int(eliminated), total, comment, json.dumps(details, ensure_ascii=False), provider, model,
        basis["偏好版本"], basis["經歷版本"], basis["模板版本"], json.dumps(basis["職缺快照"], ensure_ascii=False),
    )
    fields = ["淘汰", "總分", "評語", "評分明細", "供應商", "模型", *_BASIS_FIELDS]
    columns = ", ".join(f'"{name}"' for name in fields)
    placeholders = ", ".join("?" * len(values))
    with conn:
        conn.execute(
            f'INSERT INTO job_scores ("職缺代碼", "評分時間", {columns}) VALUES (?, ?, {placeholders})',
            (job_no, scored_at.isoformat(timespec="seconds"), *values),
        )


def list_current_scores(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    列出每筆評過分的職缺代表的評分：最新的一筆。沒評過的職缺不在其中。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: list[dict], 每筆是職缺代碼、評分時間、淘汰、總分、評語、供應商、模型與評分明細（已還原成 dict），
        依職缺代碼排序
    """
    columns = ", ".join(f'"{name}"' for name in ["職缺代碼"] + _SCORE_FIELDS + ["評分明細"])
    rows = rows_to_dicts(conn.execute(f'SELECT {columns} FROM {_CURRENT} ORDER BY "職缺代碼"'))
    for row in rows:
        row["評分明細"] = json.loads(row["評分明細"])
    return rows


def list_scores(conn: sqlite3.Connection, job_no: str) -> list[dict[str, Any]]:
    """
    取出單筆職缺的所有評分紀錄，依評分時間由新到舊（同一秒內後寫入的在前）。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param job_no: str, 職缺代碼
    :return: list[dict], 每筆是職缺代碼、評分時間、淘汰、總分、評語、供應商、模型、評分明細與評分依據的四欄；
        評分明細與職缺快照已還原成 dict，記錄依據之前的評分依據都是 None。沒有評過這筆職缺時為空清單
    """
    columns = ", ".join(f'"{name}"' for name in _HISTORY_FIELDS)
    rows = rows_to_dicts(conn.execute(
        f'SELECT {columns} FROM job_scores WHERE "職缺代碼" = ? {_LATEST_FIRST}', (job_no,),
    ))
    for row in rows:
        for name in ("評分明細", "職缺快照"):
            if row[name] is not None:
                row[name] = json.loads(row[name])
    return rows
