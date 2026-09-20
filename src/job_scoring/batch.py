"""整批評分：依輸入順序逐筆評分，單筆失敗不中斷，結果寫成 JSON 與 CSV。"""

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from job_scoring.llm import LLMClient, LLMError
from job_scoring.models import DIMENSIONS, BatchResult, Preferences
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

    :param job: dict, 爬蟲輸出的單筆職缺
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
    送給 AI 的內容與上次相同的職缺沿用上次的 AI 評分，不呼叫 AI。
    conn 為 None 時是試跑：不讀寫資料庫、不沿用上次的 AI 評分。

    :param jobs: list[dict], 爬蟲輸出的職缺
    :param prefs: Preferences, 偏好設定
    :param experience: str, experience.md 全文
    :param client_factory: callable, 建立 LLM client；第一次需要呼叫 AI 時才呼叫，整批都被淘汰或都沿用時不呼叫
    :param progress: callable, 接收每筆開始前的進度訊息
    :param conn: sqlite3.Connection or None, open_db 開啟的連線，評分結果寫入其中的 job_scores；None 表示試跑
    :param provider: str, client_factory 使用的 LLM 供應商
    :param model: str, client_factory 使用的模型名稱
    :return: list[BatchResult], 與輸入順序相同，每筆職缺一筆結果；reused 標示是否沿用上次的 AI 評分
    :raises ValueError: client_factory 不認得供應商
    :raises LLMError: client_factory 建立 client 失敗（例如缺少 API key）
    :raises sqlite3.Error: 寫入資料庫失敗；已寫入的職缺留在資料庫中
    """
    client: LLMClient | None = None

    def get_client() -> LLMClient:
        """第一次需要呼叫 AI 時才建立 client，之後重複使用"""
        nonlocal client
        if client is None:
            client = client_factory()
        return client

    results = []
    for i, job in enumerate(jobs, start=1):
        progress(f"⏳ [i] ({i}/{len(jobs)}) {job.get('職缺名稱')} - {job.get('公司名稱')}")
        fields = _job_fields(job)
        try:
            score, reused = score_and_save(job, prefs, experience, get_client, conn, provider, model)
        except (LLMError, ValidationError) as e:
            # assess 只會在 client 建好之後呼叫，client 還沒建立就拋出 LLMError，代表是建立 client 失敗
            # （例如缺少 API key）；這時每一筆都會失敗，因此不算單筆失敗，直接往外拋
            if isinstance(e, LLMError) and client is None:
                raise
            results.append(BatchResult(
                **fields, eliminated=False, elimination_reasons=[], dimensions=None,
                total=None, unknown_dimensions=[], comment=None, failure=str(e), reused=False,
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
            reused=reused,
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


def write_results(results: list[BatchResult], input_path: Path, output_dir: Path,
                  *, suffix: str = "_scored") -> tuple[Path, Path]:
    """
    把整批結果寫成 <輸入檔主體><suffix>.json 與 .csv，已存在時直接覆寫。

    :param results: list[BatchResult], 整批評分結果
    :param input_path: Path, 輸入的職缺檔，用來決定輸出檔名
    :param output_dir: Path, 輸出目錄，不存在時自動建立
    :param suffix: str, 接在輸入檔主體後的檔名後綴；試跑用另一個後綴，不覆寫正式的結果檔
    :return: tuple (Path, Path), (JSON 路徑, CSV 路徑)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{input_path.stem}{suffix}.json"
    csv_path = output_dir / f"{input_path.stem}{suffix}.csv"
    records = [r.model_dump(by_alias=True) for r in results]

    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig 在檔案開頭寫入 BOM，Excel 開啟時中文才不會亂碼
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_csv_row(record) for record in records)
    return json_path, csv_path
