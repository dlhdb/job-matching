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
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from job_db import DEFAULT_DB_PATH, SaveResult, open_db, save_run

# 輸出檔名結尾的時間戳，命名規則見功能文件的輸出檔，例如 jobs_104_Python_20260917_101500.json
_FILENAME_TIME = re.compile(r"_(\d{8}_\d{6})\.json$")


def log(message: str) -> None:
    """
    把訊息印到 stderr

    :param message: str, 要印出的訊息
    """
    print(message, file=sys.stderr)


def parse_run_time(path: str | Path) -> datetime | None:
    """
    從輸出的檔名取出執行時間

    :param path: str or Path, 檔案路徑，檔名結尾須為 _YYYYMMDD_HHMMSS.json
    :return: datetime or None, 解析不出時間時為 None
    """
    match = _FILENAME_TIME.search(Path(path).name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _load_job_file(path: Path) -> list[dict[str, Any]]:
    """
    讀取並驗證職缺 JSON

    :param path: Path, JSON 檔
    :return: list[dict], 職缺清單
    :raises ValueError: 檔案讀不到、不是 JSON，或不是職缺清單
    """
    try:
        jobs = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ValueError(f"無法讀取檔案（{e}）") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"不是合法的 JSON（{e}）") from None

    if not isinstance(jobs, list) or not jobs:
        raise ValueError("不是職缺清單，或沒有任何職缺")
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("職缺代碼"), str) or not job["職缺代碼"]:
            raise ValueError("有職缺不是物件，或缺少職缺代碼")
    return jobs


def import_json(conn: sqlite3.Connection, path: str | Path) -> SaveResult | None:
    """
    匯入一個本功能輸出的 JSON；執行時間取自檔名，同一個檔名只匯入一次。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param path: str or Path, 爬蟲輸出的 JSON 檔
    :return: SaveResult or None, 已匯入過而略過時為 None
    :raises ValueError: 檔名解析不出時間，或檔案不是合法的職缺 JSON
    """
    path = Path(path)
    run_time = parse_run_time(path)
    if run_time is None:
        raise ValueError("檔名結尾不是 _YYYYMMDD_HHMMSS.json，無法取得執行時間")

    exists = conn.execute('SELECT 1 FROM scrape_runs WHERE "來源檔" = ?', (path.name,)).fetchone()
    if exists:
        return None

    jobs = _load_job_file(path)
    return save_run(conn, jobs, run_time, "匯入", source_file=path.name)


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
    :return: int, 結束碼；沒有指定檔案、無法開啟資料庫，或所有檔案都因錯誤而略過時為 1，否則為 0
    """
    args = parse_args(argv)
    if not args.files:
        log("[-] 沒有指定要匯入的 JSON 檔")
        return 1

    handled = 0
    try:
        conn = open_db(args.db)
    except (sqlite3.Error, OSError) as e:
        log(f"[-] 無法開啟資料庫 {args.db}：{e}")
        return 1
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
