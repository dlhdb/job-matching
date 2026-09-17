#!/usr/bin/env python3
"""
職缺評分工具
-------------------------
讀取爬蟲輸出的職缺 JSON 與 profile/ 的個人資料，對職缺評分。
- 單筆：把 JobScore JSON 印到 stdout。
- 整批：結果寫成 output/scores/ 下的 JSON 與 CSV，stdout 不輸出。
進度、摘要與錯誤訊息印到 stderr，可以把 stdout 直接導向檔案。

使用說明：
- 評分整批職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json`
- 只評一筆職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json --job-no 8s12x`
- 只看提示詞（不呼叫 AI）：指定 `--job-no` 並加上 `--dry-run`
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from job_scoring.batch import NeverCalledClient, score_batch, write_results
from job_scoring.jobs import find_job, load_jobs
from job_scoring.llm import DEFAULT_MODEL, DEFAULT_PROVIDER, LLMError, get_client
from job_scoring.models import Preferences
from job_scoring.profile import ProfileError, load_experience, load_preferences
from job_scoring.prompt import build_prompt
from job_scoring.rules import check_hard_filters, score_salary
from job_scoring.scorer import score_job

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
                        help="只印出提示詞，不建立 LLM client、不發出網路請求；必須搭配 --job-no")
    return parser.parse_args(argv)


def print_dry_run(job: dict[str, Any], prefs: Preferences, experience: str) -> None:
    """
    先印出淘汰與薪資的判斷（stderr），再把完整提示詞印到 stdout

    :param job: dict, 職缺資料
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    """
    reasons = check_hard_filters(job, prefs)
    if reasons:
        log(f"[!] 此職缺會被淘汰，實際評分時不會呼叫 AI：{'；'.join(reasons)}")
    else:
        salary_score, salary_reason = score_salary(job, prefs)
        log(f"[i] 薪資水準：{salary_score}（{salary_reason}）")

    system, user = build_prompt(job, prefs, experience)
    print("===== SYSTEM =====")
    print(system)
    print("\n===== USER =====")
    print(user)


def run_single(args: argparse.Namespace, job: dict[str, Any], prefs: Preferences, experience: str) -> int:
    """
    評單筆職缺，把結果 JSON 印到 stdout

    :param args: argparse.Namespace, 命令列參數
    :param job: dict, 職缺資料
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :return: int, 結束碼
    """
    try:
        if check_hard_filters(job, prefs):
            # 被淘汰的職缺不會呼叫 AI，不需要建立 client（也就不需要 API key）
            result = score_job(job, prefs, experience, client=NeverCalledClient())
        else:
            client = get_client(args.provider, args.model)
            log(f"⏳ 正在以 {args.provider}/{args.model} 評分職缺 {job.get('職缺代碼')}：{job.get('職缺名稱')}")
            result = score_job(job, prefs, experience, client)
    except ValidationError as e:
        # ValidationError 是 ValueError 的子類別，必須先攔截
        log(f"[-] AI 回應不符合評分格式，本次評分失敗：\n{e}")
        return 1
    except (LLMError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
    if result.eliminated:
        log(f"[i] 職缺已淘汰：{'；'.join(result.elimination_reasons)}")
    else:
        log(f"🎉 評分完成，總分：{result.total}")
    return 0


def run_batch(args: argparse.Namespace, jobs: list[dict[str, Any]], prefs: Preferences, experience: str) -> int:
    """
    評整批職缺，寫出結果檔並把摘要印到 stderr

    :param args: argparse.Namespace, 命令列參數
    :param jobs: list[dict], 職缺清單
    :param prefs: Preferences, 偏好設定
    :param experience: str, 經歷全文
    :return: int, 結束碼；單筆評分失敗仍回傳 0，只有 client 建立失敗回傳 1
    """
    log(f"⏳ 正在以 {args.provider}/{args.model} 評分 {len(jobs)} 筆職缺")
    try:
        # 以 lambda 延後查找 get_client，第一次需要呼叫 AI 時才建立 client
        results = score_batch(jobs, prefs, experience, lambda: get_client(args.provider, args.model), log)
    except (LLMError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    json_path, csv_path = write_results(results, args.jobs, SCORES_DIR)
    eliminated = sum(r.eliminated for r in results)
    failed = [r for r in results if r.failure is not None]
    succeeded = len(results) - eliminated - len(failed)
    log(f"🎉 [+] 評分完成：共 {len(results)} 筆，成功 {succeeded}、淘汰 {eliminated}、失敗 {len(failed)}")
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
    if args.dry_run and args.job_no is None:
        log("[-] --dry-run 必須搭配 --job-no，一次只印出一筆職缺的提示詞")
        return 1
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

    if job is None:
        return run_batch(args, jobs, prefs, experience)
    if args.dry_run:
        print_dry_run(job, prefs, experience)
        return 0
    return run_single(args, job, prefs, experience)


if __name__ == "__main__":
    sys.exit(main())
