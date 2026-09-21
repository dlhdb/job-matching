#!/usr/bin/env python3
"""
職缺評分工具
-------------------------
從職缺資料庫（預設 data/jobs.db）讀取職缺，依 profile/ 的個人資料評分。
- 不指定 --job-no：評所有還沒有任何評分的職缺，依最後出現時間由新到舊。
- 指定 --job-no：只評這幾筆，已經評過的也照樣重評。
每次評分都新增一筆評分紀錄寫進同一個資料庫，不覆寫任何紀錄；不論評幾筆，終端機都只顯示進度與摘要。
試跑（--dry-run）照常評分，但不寫入資料庫，結果寫成 output/scores/ 下的 dryrun_<開始時間> 結果檔。
進度、摘要與錯誤訊息都印到 stderr。

使用說明：
- 評所有還沒評分的職缺：`uv run src/score_job.py`
- 只評指定的職缺：`uv run src/score_job.py --job-no 8s12x 7abcd`
- 使用其他資料庫：加上 `--db <路徑>`
- 換偏好、經歷或模型試跑，不影響已存的評分：`uv run src/score_job.py --job-no 8s12x --dry-run`
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from job_db import DEFAULT_DB_PATH, get_job, list_unscored_jobs, open_db, open_db_readonly
from job_scoring.batch import score_batch, write_dry_run_results
from job_scoring.llm import DEFAULT_MODEL, DEFAULT_PROVIDER, LLMError, get_client
from job_scoring.models import Preferences
from job_scoring.profile import ProfileError, load_experience, load_preferences

# 以腳本位置為基準，不受執行時的工作目錄影響
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "profile"
SCORES_DIR = PROJECT_ROOT / "output" / "scores"


def log(message: str) -> None:
    """
    把進度或錯誤訊息印到 stderr，讓 stdout 只保留結果

    :param message: str, 要印出的訊息
    """
    print(message, file=sys.stderr)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    解析命令列參數

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: argparse.Namespace, 解析結果
    """
    parser = argparse.ArgumentParser(description="從職缺資料庫讀取職缺並評分")
    parser.add_argument("--job-no", nargs="+",
                        help="只評這幾筆職缺代碼，以空白分隔；省略時評所有還沒評分的職缺")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR,
                        help="放 preferences.yaml 與 experience.md 的目錄（預設為專案根目錄下的 profile/）")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"LLM 供應商（預設 {DEFAULT_PROVIDER}）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名稱（預設 {DEFAULT_MODEL}）")
    parser.add_argument("--dry-run", action="store_true",
                        help="試跑：照常評分（會呼叫 AI），但不寫入資料庫，結果寫成 output/scores/ 下的試跑結果檔；"
                             "必須搭配 --job-no")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="讀取職缺與寫入評分的資料庫（預設為專案根目錄的 data/jobs.db）")
    return parser.parse_args(argv)


def select_jobs(conn: sqlite3.Connection, job_nos: list[str] | None) -> list[dict[str, Any]]:
    """
    選出要評的職缺

    :param conn: sqlite3.Connection, 資料庫連線
    :param job_nos: list[str] or None, 指定的職缺代碼；None 時選所有還沒評分的職缺
    :return: list[dict], 依指定順序（重複的只留一次）或最後出現時間由新到舊排列的職缺
    :raises ValueError: 有指定的職缺代碼不在職缺資料庫
    """
    if job_nos is None:
        return list_unscored_jobs(conn)
    # dict.fromkeys 保留第一次出現的順序，重複指定的只評一次
    unique = list(dict.fromkeys(job_nos))
    found = {job_no: get_job(conn, job_no) for job_no in unique}
    missing = [job_no for job_no, job in found.items() if job is None]
    if missing:
        raise ValueError(f"職缺資料庫中找不到職缺代碼：{'、'.join(missing)}，沒有評任何一筆")
    return [job for job in found.values() if job is not None]


def run(args: argparse.Namespace, jobs: list[dict[str, Any]], prefs: Preferences, experience: str,
        conn: sqlite3.Connection | None) -> int:
    """
    逐筆評分並寫入資料庫，把摘要印到 stderr；試跑時改寫成試跑結果檔

    :param args: argparse.Namespace, 命令列參數
    :param jobs: list[dict], 要評的職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :param conn: sqlite3.Connection or None, 評分結果寫入的資料庫連線；None 表示試跑
    :return: int, 結束碼；單筆評分失敗仍回傳 0，client 建立失敗或寫入資料庫失敗回傳 1
    """
    started_at = datetime.now()
    if conn is None:
        log("[i] 試跑：不寫入資料庫，不影響已存的評分")
    log(f"⏳ 正在以 {args.provider}/{args.model} 評分 {len(jobs)} 筆職缺")
    try:
        results = score_batch(jobs, prefs, experience, lambda: get_client(args.provider, args.model), log,
                              conn=conn, provider=args.provider, model=args.model)
    except sqlite3.Error as e:
        # 已評完的職缺各自寫入，留在資料庫中
        log(f"[-] 讀寫資料庫失敗，已中止評分：{e}")
        return 1
    except (LLMError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    eliminated = sum(r.eliminated for r in results)
    failed = [r for r in results if r.failure is not None]
    succeeded = len(results) - eliminated - len(failed)
    log(f"🎉 [+] 評分完成：共 {len(results)} 筆，成功 {succeeded}、淘汰 {eliminated}、失敗 {len(failed)}")
    for r in failed:
        log(f"[!] {r.job_no} {r.job_name}：{r.failure}")
    if conn is None:
        json_path, csv_path = write_dry_run_results(results, SCORES_DIR, started_at)
        log(f"[i] JSON：{json_path}")
        log(f"[i] CSV：{csv_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    CLI 進入點。

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: int, 結束碼；成功（包括被淘汰、有職缺評分失敗）為 0，失敗為 1
    """
    args = parse_args(argv)
    # 不覆寫已存在的環境變數，shell 設定的值優先
    load_dotenv(PROJECT_ROOT / ".env")
    db_path = args.db

    try:
        prefs = load_preferences(args.profile_dir / "preferences.yaml")
        experience = load_experience(args.profile_dir / "experience.md")
    except (ProfileError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    if args.dry_run and args.job_no is None:
        log("[-] 試跑必須以 --job-no 指定要評的職缺")
        return 1
    if not db_path.exists():
        # 不讓 open_db 建立空的資料庫：裡面沒有職缺，評分也沒有意義
        log(f"[-] 找不到資料庫 {db_path}，請先用爬蟲或匯入指令寫入職缺")
        return 1

    try:
        conn = open_db_readonly(db_path) if args.dry_run else open_db(db_path)
    except (sqlite3.Error, OSError) as e:
        log(f"[-] 無法開啟資料庫 {db_path}：{e}")
        return 1
    with closing(conn):
        try:
            jobs = select_jobs(conn, args.job_no)
        except ValueError as e:
            log(f"[-] {e}")
            return 1
        except sqlite3.Error as e:
            log(f"[-] 讀取職缺失敗：{e}")
            return 1
        if not jobs:
            log("[i] 沒有還沒評分的職缺")
            return 0
        return run(args, jobs, prefs, experience, None if args.dry_run else conn)


if __name__ == "__main__":
    sys.exit(main())
