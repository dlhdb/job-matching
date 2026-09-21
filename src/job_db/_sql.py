"""查詢共用的 SQL 組裝，與哪一張表無關。"""

import sqlite3
from typing import Any


def rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """
    把查詢結果轉成以欄名為鍵的 dict

    :param cursor: sqlite3.Cursor, 已執行的查詢
    :return: list[dict], 每列一個 dict，鍵是欄名
    """
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def limit_clause(limit: int | None, offset: int | None) -> tuple[str, list[Any]]:
    """
    組出 LIMIT／OFFSET 子句

    :param limit: int or None, 最多取幾筆；None 代表不限
    :param offset: int or None, 從第幾筆開始；None 代表從頭
    :return: tuple (str, list), 接在查詢尾端的子句與對應的參數
    :raises ValueError: limit 或 offset 是負數
    """
    # SQLite 把負的 LIMIT 當成不限筆數，不擋下來會靜默回傳全部
    if (limit is not None and limit < 0) or (offset is not None and offset < 0):
        raise ValueError(f"limit 與 offset 不可為負數：limit={limit}, offset={offset}")
    if limit is None and offset is None:
        return "", []
    if offset is None:
        return " LIMIT ?", [limit]
    # SQLite 要有 LIMIT 才能用 OFFSET，只給 offset 時以 -1 代表不限筆數
    return " LIMIT ? OFFSET ?", [-1 if limit is None else limit, offset]
