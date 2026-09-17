#!/usr/bin/env python3
"""
職缺匯入工具
-------------------------
把爬蟲先前輸出的職缺 JSON 匯入職缺資料庫，執行時間取自檔名。
同一個檔案重複匯入時會略過；無法匯入的檔案印出警告後繼續處理下一個。
訊息一律印到 stderr。

使用說明：
- `uv run src/import_jobs.py output/104/*.json`
- 指定資料庫：`uv run src/import_jobs.py output/104/*.json --db data/jobs.db`
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from job_db import DEFAULT_DB_PATH, import_json, open_db


def log(message: str) -> None:
    """
    把訊息印到 stderr

    :param message: str, 要印出的訊息
    """
    print(message, file=sys.stderr)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    解析命令列參數

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: argparse.Namespace, 解析結果
    """
    parser = argparse.ArgumentParser(description="把爬蟲輸出的職缺 JSON 匯入職缺資料庫")
    parser.add_argument("files", nargs="*", type=Path, help="爬蟲輸出的 JSON 檔，可指定多個")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="資料庫路徑（預設為專案根目錄下的 data/jobs.db）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    CLI 進入點。

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: int, 結束碼；沒有指定檔案或所有檔案都因錯誤而略過時為 1，否則為 0
    """
    args = parse_args(argv)
    if not args.files:
        log("[-] 沒有指定要匯入的 JSON 檔")
        return 1

    handled = 0
    conn = open_db(args.db)
    try:
        for path in args.files:
            log(f"⏳ 正在匯入 {path.name}")
            try:
                result = import_json(conn, path)
            except (ValueError, sqlite3.Error) as e:
                log(f"[!] 略過 {path.name}：{e}")
                continue
            handled += 1
            if result is None:
                log(f"[i] 已匯入過，略過 {path.name}")
    finally:
        conn.close()

    if handled == 0:
        log("[-] 沒有任何檔案匯入成功")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
