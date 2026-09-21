"""整批評分：依輸入順序逐筆評分，單筆失敗不中斷；試跑的結果寫成 JSON 與 CSV。"""

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from job_scoring.llm import LLMClient, LLMError
from job_scoring.models import DIMENSIONS, BatchResult, Preferences
from job_scoring.rules import check_hard_filters
from job_scoring.scorer import score_and_save

# CSV 欄位順序；四個維度欄只放分數，理由要查 JSON
CSV_FIELDNAMES = [
    "職缺代碼", "職缺名稱", "公司名稱", "薪資待遇",
    "總分", *DIMENSIONS,
    "未知維度", "淘汰原因",
    "評語", "失敗原因", "職缺連結",
]


def _job_fields(job: dict[str, Any]) -> dict[str, Any]:
    """
    取出結果檔要從輸入職缺原樣帶入的欄位

    :param job: dict, 符合職缺欄位契約的單筆職缺
    :return: dict, BatchResult 的建構參數
    """
    return {
        "job_no": str(job.get("職缺代碼") or ""),
        "job_name": job.get("職缺名稱"),
        "company": job.get("公司名稱"),
        "salary_text": job.get("薪資待遇"),
        "job_url": job.get("職缺連結"),
    }


def score_batch(
    jobs: list[dict[str, Any]],
    prefs: Preferences,
    experience: str,
    client_factory: Callable[[], LLMClient],
    progress: Callable[[str], None],
    *,
    conn: sqlite3.Connection | None,
    provider: str,
    model: str,
) -> list[BatchResult]:
    """
    依輸入順序逐筆評分，每筆評完就寫入 job_scores；LLM 呼叫失敗或回應驗證失敗時記下原因並繼續下一筆（不寫入）。
    conn 為 None 時是試跑：只評分，不寫入資料庫。

    有需要呼叫 AI 的職缺時，開始評分前就建立 client：建立失敗（例如缺少 API key）時每一筆都會失敗，
    所以直接往外拋，這時還沒有寫入任何一筆。

    :param jobs: list[dict], 符合職缺欄位契約的職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client_factory: callable, 建立 LLM client；整批都被淘汰時不呼叫
    :param progress: callable, 接收每筆開始前的進度訊息
    :param conn: sqlite3.Connection or None, open_db 開啟的連線，評分結果寫入其中的 job_scores；None 表示試跑
    :param provider: str, client_factory 使用的 LLM 供應商
    :param model: str, client_factory 使用的模型名稱
    :return: list[BatchResult], 與輸入順序相同，每筆職缺一筆結果
    :raises ValueError: client_factory 不認得供應商
    :raises LLMError: client_factory 建立 client 失敗（例如缺少 API key）
    :raises sqlite3.Error: 寫入資料庫失敗；已寫入的職缺留在資料庫中
    """
    needs_ai = any(not check_hard_filters(job, prefs) for job in jobs)
    client = client_factory() if needs_ai else None

    results = []
    for i, job in enumerate(jobs, start=1):
        progress(f"⏳ [i] ({i}/{len(jobs)}) {job.get('職缺名稱')} - {job.get('公司名稱')}")
        fields = _job_fields(job)
        try:
            score = score_and_save(job, prefs, experience, client, conn, provider, model)
        except (LLMError, ValidationError) as e:
            results.append(BatchResult(
                **fields, eliminated=False, elimination_reasons=[], dimensions=None,
                total=None, unknown_dimensions=[], comment=None, failure=str(e),
            ))
            continue

        results.append(BatchResult(
            **fields,
            eliminated=score.eliminated,
            elimination_reasons=score.elimination_reasons,
            dimensions=score.dimensions,
            total=score.total,
            unknown_dimensions=score.unknown_dimensions,
            comment=score.comment,
            failure=None,
        ))
    return results


def _csv_row(record: dict[str, Any]) -> dict[str, Any]:
    """
    把一筆結果（中文鍵名的 dict）轉成 CSV 列；未知分數與 None 都寫成空字串

    :param record: dict, BatchResult.model_dump(by_alias=True) 的結果
    :return: dict, CSV 欄位 → 值
    """
    dimensions = record["維度"] or {}
    row = {name: record[name] for name in ("職缺代碼", "職缺名稱", "公司名稱", "薪資待遇",
                                             "總分", "評語", "失敗原因", "職缺連結")}
    for name in DIMENSIONS:
        row[name] = dimensions[name]["分數"] if name in dimensions else None
    row["未知維度"] = ", ".join(record["未知維度"])
    row["淘汰原因"] = ", ".join(record["淘汰原因"])
    return {k: "" if v is None else v for k, v in row.items()}


def _free_stem(output_dir: Path, stem: str) -> str:
    """
    找出 .json 與 .csv 都還不存在的檔名主體：先用 stem，已存在時依序加上 _2、_3……

    :param output_dir: Path, 輸出目錄
    :param stem: str, 檔名主體
    :return: str, 可用的檔名主體
    """
    candidate, n = stem, 1
    while (output_dir / f"{candidate}.json").exists() or (output_dir / f"{candidate}.csv").exists():
        n += 1
        candidate = f"{stem}_{n}"
    return candidate


def write_dry_run_results(results: list[BatchResult], output_dir: Path, started_at: datetime) -> tuple[Path, Path]:
    """
    把試跑結果寫成 dryrun_<開始時間>.json 與 .csv；同名的檔案已經存在時加上流水號，不覆寫。

    :param results: list[BatchResult], 試跑的評分結果
    :param output_dir: Path, 輸出目錄，不存在時自動建立
    :param started_at: datetime, 試跑開始的時間，決定檔名
    :return: tuple (Path, Path), (JSON 路徑, CSV 路徑)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _free_stem(output_dir, f"dryrun_{started_at:%Y%m%d_%H%M%S}")
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    records = [r.model_dump(by_alias=True) for r in results]

    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig 在檔案開頭寫入 BOM，Excel 開啟時中文才不會亂碼
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_csv_row(record) for record in records)
    return json_path, csv_path
