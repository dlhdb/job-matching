#!/usr/bin/env python3
"""
單筆職缺評分工具
-------------------------
讀取爬蟲輸出的職缺 JSON 與 profile/ 的個人資料，對一筆職缺評分，並把 JobScore JSON 印到 stdout。
進度與錯誤訊息印到 stderr，可以把 stdout 直接導向檔案。

使用說明：
- 評分第一筆職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json`
- 指定職缺：`uv run src/score_job.py --jobs output/104/<檔名>.json --job-no 8s12x`
- 只看提示詞（不呼叫 AI）：加上 `--dry-run`
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from job_scoring.llm import DEFAULT_MODEL, DEFAULT_PROVIDER, LLMError, get_client
from job_scoring.models import Preferences
from job_scoring.profile import ProfileError, load_experience, load_preferences
from job_scoring.prompt import build_prompt
from job_scoring.rules import check_hard_filters, score_salary
from job_scoring.scorer import score_job

# 以腳本位置為基準，不受執行時的工作目錄影響
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "profile"


def log(message: str) -> None:
    """
    把進度或錯誤訊息印到 stderr，讓 stdout 只保留結果

    :param message: str, 要印出的訊息
    """
    print(message, file=sys.stderr)


def load_job(jobs_path: Path, job_no: str | None) -> dict[str, Any]:
    """
    從爬蟲輸出的 JSON 中取出一筆職缺。

    :param jobs_path: Path, 爬蟲輸出的 JSON 檔
    :param job_no: str or None, 職缺代碼；None 時取第一筆
    :return: dict, 職缺資料
    :raises ValueError: 檔案不存在、格式錯誤、沒有職缺，或找不到指定的職缺代碼
    """
    try:
        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"找不到職缺檔：{jobs_path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"職缺檔不是合法的 JSON：{jobs_path}（{e}）") from None

    if not isinstance(jobs, list) or not jobs:
        raise ValueError(f"職缺檔沒有任何職缺：{jobs_path}")
    if not all(isinstance(job, dict) for job in jobs):
        raise ValueError(f"職缺檔格式錯誤，每筆職缺都必須是物件：{jobs_path}")
    if job_no is None:
        return jobs[0]
    for job in jobs:
        if str(job.get("職缺代碼")) == job_no:
            return job
    raise ValueError(f"職缺檔中找不到職缺代碼 {job_no}：{jobs_path}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    解析命令列參數

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: argparse.Namespace, 解析結果
    """
    parser = argparse.ArgumentParser(description="對單筆職缺評分")
    parser.add_argument("--jobs", required=True, type=Path, help="爬蟲輸出的 JSON 檔")
    parser.add_argument("--job-no", help="要評分的職缺代碼；省略時使用第一筆")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR,
                        help="放 preferences.yaml 與 experience.md 的目錄（預設為專案根目錄下的 profile/）")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"LLM 供應商（預設 {DEFAULT_PROVIDER}）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名稱（預設 {DEFAULT_MODEL}）")
    parser.add_argument("--dry-run", action="store_true", help="只印出提示詞，不建立 LLM client、不發出網路請求")
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


def main(argv: list[str] | None = None) -> int:
    """
    CLI 進入點。

    :param argv: list[str] or None, 命令列參數；None 時使用 sys.argv
    :return: int, 結束碼；成功（包括被淘汰）為 0，失敗為 1
    """
    args = parse_args(argv)
    # 不覆寫已存在的環境變數，shell 設定的值優先
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        prefs = load_preferences(args.profile_dir / "preferences.yaml")
        experience = load_experience(args.profile_dir / "experience.md")
        job = load_job(args.jobs, args.job_no)
    except (ProfileError, ValueError) as e:
        log(f"[-] {e}")
        return 1

    if args.dry_run:
        print_dry_run(job, prefs, experience)
        return 0

    try:
        if check_hard_filters(job, prefs):
            # 被淘汰的職缺不會呼叫 AI，不需要建立 client（也就不需要 API key）
            result = score_job(job, prefs, experience, client=_NeverCalledClient())
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


class _NeverCalledClient:
    """被淘汰的職缺使用的佔位 client；score_job 不會呼叫它，被呼叫就代表流程有錯"""

    def assess(self, system: str, user: str) -> Any:
        raise AssertionError("被淘汰的職缺不應呼叫 LLM")


if __name__ == "__main__":
    sys.exit(main())
