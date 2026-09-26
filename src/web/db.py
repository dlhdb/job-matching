"""API 共用的資料庫連線。"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager

from fastapi import Request

from job_db import open_db


@contextmanager
def connect(request: Request) -> Iterator[sqlite3.Connection]:
    """
    為這個請求開一條職缺資料庫的連線，離開 with 區塊時關閉

    在端點裡開、在端點裡關：同步端點跑在 threadpool，sqlite3 的連線不能跨執行緒使用，
    交給 FastAPI 的 dependency 開的話，開與用可能在不同的執行緒。

    :param request: Request, 目前的請求，從 app.state.db_path 取得資料庫路徑
    :return: Iterator[sqlite3.Connection]
    """
    with closing(open_db(request.app.state.db_path)) as conn:
        yield conn
