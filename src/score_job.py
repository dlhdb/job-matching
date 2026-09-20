#!/usr/bin/env python3
"""
職缺評分工具
-------------------------
讀取爬蟲輸出的職缺 JSON 與 profile/ 的個人資料，對職缺評分。
- 單筆：把 JobScore JSON 印到 stdout。
- 整批：結果寫成 output/scores/ 下的 JSON 與 CSV，stdout 不輸出。
單筆與整批的結果都寫入資料庫（預設 data/jobs.db）的 job_scores，每筆職缺只留最新一次。
送給 AI 的內容與上次相同的職缺，沿用資料庫中上次的 AI 評分，不再呼叫 AI。
試跑（--dry-run）照常評分，但不讀寫資料庫；單筆與整批都寫成 output/scores/ 下的 _dryrun 結果檔。
進度、摘要與錯誤訊息印到 stderr，可以把 stdout 直接導向檔案。

使用說明：
- 評分整批職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json`
- 只評一筆職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json --job-no 8s12x`
- 寫入其他資料庫：加上 `--db <路徑>`
- 換偏好、經歷或模型試跑，不影響已存的評分：加上 `--dry-run`
"""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from job_db import DEFAULT_DB_PATH, open_db
from job_scoring.batch import score_batch, write_results
from job_scoring.jobs import find_job, load_jobs
from job_scoring.llm import DEFAULT_MODEL, DEFAULT_PROVIDER, LLMClient, LLMError, get_client
from job_scoring.models import Preferences
from job_scoring.profile import ProfileError, load_experience, load_preferences
from job_scoring.scorer import score_and_save

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
    parser = argparse.ArgumentParser(description="對單筆或整批職缺評分")
    parser.add_argument("--jobs", required=True, type=Path, help="爬蟲輸出的 JSON 檔")
    parser.add_argument("--job-no", help="只評這筆職缺代碼；省略時評整批，結果寫到 output/scores/")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR,
                        help="放 preferences.yaml 與 experience.md 的目錄（預設為專案根目錄下的 profile/）")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"LLM 供應商（預設 {DEFAULT_PROVIDER}）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名稱（預設 {DEFAULT_MODEL}）")
    parser.add_argument("--dry-run", action="store_true",
                        help="試跑：照常評分（會呼叫 AI），但不讀寫資料庫、不沿用上次的 AI 評分；"
                             "單筆與整批都寫成 _dryrun 結果檔")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="評分結果寫入的資料庫（預設為專案根目錄的 data/jobs.db）")
    return parser.parse_args(argv)


def run_single(args: argparse.Namespace, job: dict[str, Any], prefs: Preferences, experience: str,
               conn: sqlite3.Connection) -> int:
    """
    評單筆職缺並寫入資料庫，把結果 JSON 印到 stdout

    :param args: argparse.Namespace, 命令列參數
    :param job: dict, 職缺資料
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :param conn: sqlite3.Connection, 評分結果寫入的資料庫連線
    :return: int, 結束碼
    """
    def client_factory() -> LLMClient:
        # 被淘汰或沿用上次的 AI 評分時不會呼叫，也就不需要 API key
        client = get_client(args.provider, args.model)
        log(f"⏳ 正在以 {args.provider}/{args.model} 評分職缺 {job.get('職缺代碼')}：{job.get('職缺名稱')}")
        return client

    try:
        result, reused = score_and_save(job, prefs, experience, client_factory, conn, args.provider, args.model)
    except sqlite3.Error as e:
        log(f"[-] 讀寫資料庫失敗：{e}")
        return 1
    except ValidationError as e:
        # ValidationError 是 ValueError 的子類別，必須先攔截
        log(f"[-] AI 回應不符合評分格式，本次評分失敗：\n{e}")
        return 1
    except (LLMError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
    if reused:
        log("[i] 沿用上次的 AI 評分結果，未呼叫 AI")
    if result.eliminated:
        log(f"[i] 職缺已淘汰：{'；'.join(result.elimination_reasons)}")
    else:
        log(f"🎉 評分完成，總分：{result.total}")
    return 0


def run_batch(args: argparse.Namespace, jobs: list[dict[str, Any]], prefs: Preferences, experience: str,
              conn: sqlite3.Connection | None) -> int:
    """
    評整批職缺並逐筆寫入資料庫，寫出結果檔並把摘要印到 stderr

    :param args: argparse.Namespace, 命令列參數
    :param jobs: list[dict], 職缺清單
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :param conn: sqlite3.Connection or None, 評分結果寫入的資料庫連線；None 表示試跑，結果檔改用 _dryrun 後綴
    :return: int, 結束碼；單筆評分失敗仍回傳 0，client 建立失敗或寫入資料庫失敗回傳 1
    """
    if conn is None:
        log("[i] 試跑：不讀寫資料庫，不影響已存的評分")
    log(f"⏳ 正在以 {args.provider}/{args.model} 評分 {len(jobs)} 筆職缺")
    try:
        # 以 lambda 延後查找 get_client，第一次需要呼叫 AI 時才建立 client
        results = score_batch(jobs, prefs, experience, lambda: get_client(args.provider, args.model), log,
                              conn=conn, provider=args.provider, model=args.model)
    except sqlite3.Error as e:
        # 已評完的職缺各自寫入，留在資料庫中；結果檔不完整，因此不寫出
        log(f"[-] 讀寫資料庫失敗，已中止評分：{e}")
        return 1
    except (LLMError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    json_path, csv_path = write_results(results, args.jobs, SCORES_DIR,
                                        suffix="_dryrun" if conn is None else "_scored")
    eliminated = sum(r.eliminated for r in results)
    failed = [r for r in results if r.failure is not None]
    succeeded = len(results) - eliminated - len(failed)
    log(f"🎉 [+] 評分完成：共 {len(results)} 筆，成功 {succeeded}、淘汰 {eliminated}、失敗 {len(failed)}")
    reused = sum(r.reused for r in results)
    if reused:
        # 沿用的筆數算在成功裡
        log(f"[i] 沿用上次的 AI 評分：{reused} 筆")
    for r in failed:
        log(f"[!] {r.job_no} {r.job_name}：{r.failure}")
    log(f"[i] JSON：{json_path}")
    log(f"[i] CSV：{csv_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    CLI 進入點。

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: int, 結束碼；成功（包括被淘汰、整批中有單筆失敗）為 0，失敗為 1
    """
    args = parse_args(argv)
    # 不覆寫已存在的環境變數，shell 設定的值優先
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        prefs = load_preferences(args.profile_dir / "preferences.yaml")
        experience = load_experience(args.profile_dir / "experience.md")
        jobs = load_jobs(args.jobs)
        job = find_job(jobs, args.job_no) if args.job_no is not None else None
    except (ProfileError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    if args.dry_run:
        # 試跑不開啟資料庫；單筆也當成只有一筆的整批，同樣寫成結果檔
        return run_batch(args, jobs if job is None else [job], prefs, experience, None)

    try:
        conn = open_db(args.db)
    except (sqlite3.Error, OSError) as e:
        log(f"[-] 無法開啟資料庫 {args.db}：{e}")
        return 1
    with closing(conn):
        if job is None:
            return run_batch(args, jobs, prefs, experience, conn)
        return run_single(args, job, prefs, experience, conn)


if __name__ == "__main__":
    sys.exit(main())
