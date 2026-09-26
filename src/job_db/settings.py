"""讀寫評分用的設定（settings_versions、current_settings）：每次儲存新增一個版本，目前設定指向其中一版。

版本只新增、不刪除，評分紀錄記下的版本永遠查得到；版本的內容不能改，只能改名稱與描述。
"""

import sqlite3
from datetime import datetime
from typing import Any

from job_db._sql import rows_to_dicts

_VERSION_FIELDS = ["版本", "名稱", "描述", "儲存時間", "內容"]
_COLUMNS = ", ".join(f'"{name}"' for name in _VERSION_FIELDS)


def _check_name(name: str) -> None:
    """
    :param name: str, 版本的名稱
    :raises ValueError: 名稱是空的或只有空白
    """
    if not name.strip():
        raise ValueError("版本的名稱必填")


def list_versions(conn: sqlite3.Connection, kind: str) -> list[dict[str, Any]]:
    """
    列出一種設定的所有版本，由新到舊

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param kind: str, 設定的種類（preferences、experience、template）
    :return: list[dict], 每筆是版本、名稱、描述、儲存時間、內容；還沒有版本時為空清單
    """
    return rows_to_dicts(conn.execute(
        f'SELECT {_COLUMNS} FROM settings_versions WHERE "種類" = ? ORDER BY "版本" DESC', (kind,),
    ))


def get_version(conn: sqlite3.Connection, kind: str, version: int) -> dict[str, Any] | None:
    """
    取出一種設定的某一版

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param kind: str, 設定的種類
    :param version: int, 版本
    :return: dict or None, 版本、名稱、描述、儲存時間、內容；沒有這一版時為 None
    """
    rows = rows_to_dicts(conn.execute(
        f'SELECT {_COLUMNS} FROM settings_versions WHERE "種類" = ? AND "版本" = ?', (kind, version),
    ))
    return rows[0] if rows else None


def current_versions(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """
    取出每種設定目前用的版本

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: dict, 種類 → 版本、名稱、描述、儲存時間、內容；還沒有目前設定的種類不在其中
    """
    columns = ", ".join(f'v."{name}"' for name in _VERSION_FIELDS)
    rows = rows_to_dicts(conn.execute(
        f'SELECT c."種類", {columns} FROM current_settings AS c '
        'JOIN settings_versions AS v ON v."種類" = c."種類" AND v."版本" = c."版本"'
    ))
    return {row.pop("種類"): row for row in rows}


def _set_current(conn: sqlite3.Connection, kind: str, version: int) -> None:
    conn.execute(
        'INSERT INTO current_settings ("種類", "版本") VALUES (?, ?) '
        'ON CONFLICT ("種類") DO UPDATE SET "版本" = excluded."版本"',
        (kind, version),
    )


def add_version(
    conn: sqlite3.Connection,
    kind: str,
    *,
    name: str,
    description: str,
    content: str,
    saved_at: datetime,
) -> int:
    """
    新增一版並改成目前設定；即使內容和其他版本相同也新增。新增與套用在同一個交易中。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param kind: str, 設定的種類
    :param name: str, 名稱，必填
    :param description: str, 描述，可以是空字串
    :param content: str, 內容
    :param saved_at: datetime, 儲存時間（本地時間）
    :return: int, 新版本的編號，從 1 開始遞增
    :raises ValueError: 名稱是空的，資料庫不變
    """
    _check_name(name)
    with conn:
        version = conn.execute(
            'SELECT COALESCE(MAX("版本"), 0) + 1 FROM settings_versions WHERE "種類" = ?', (kind,),
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO settings_versions ("種類", "版本", "名稱", "描述", "儲存時間", "內容") '
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, version, name, description, saved_at.isoformat(timespec="seconds"), content),
        )
        _set_current(conn, kind, version)
    return version


def apply_version(conn: sqlite3.Connection, kind: str, version: int) -> None:
    """
    把某一版改成目前設定，不新增版本

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param kind: str, 設定的種類
    :param version: int, 版本
    :raises LookupError: 沒有這一版，資料庫不變
    """
    if get_version(conn, kind, version) is None:
        raise LookupError(f"沒有第 {version} 版")
    with conn:
        _set_current(conn, kind, version)


def update_version_meta(conn: sqlite3.Connection, kind: str, version: int, *, name: str, description: str) -> None:
    """
    修改某一版的名稱與描述；內容不變

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param kind: str, 設定的種類
    :param version: int, 版本
    :param name: str, 名稱，必填
    :param description: str, 描述，可以是空字串
    :raises ValueError: 名稱是空的，資料庫不變
    :raises LookupError: 沒有這一版，資料庫不變
    """
    _check_name(name)
    with conn:
        cursor = conn.execute(
            'UPDATE settings_versions SET "名稱" = ?, "描述" = ? WHERE "種類" = ? AND "版本" = ?',
            (name, description, kind, version),
        )
    if cursor.rowcount == 0:
        raise LookupError(f"沒有第 {version} 版")


def init_defaults(conn: sqlite3.Connection, defaults: dict[str, tuple[str, str, str]], saved_at: datetime) -> list[str]:
    """
    替還沒有任何版本的種類寫入第 1 版並設成目前設定；已經有版本的種類不動

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param defaults: dict, 種類 → (名稱, 描述, 內容)
    :param saved_at: datetime, 儲存時間（本地時間）
    :return: list[str], 這次寫入第 1 版的種類
    """
    added = []
    for kind, (name, description, content) in defaults.items():
        exists = conn.execute('SELECT 1 FROM settings_versions WHERE "種類" = ? LIMIT 1', (kind,)).fetchone()
        if exists is None:
            add_version(conn, kind, name=name, description=description, content=content, saved_at=saved_at)
            added.append(kind)
    return added
