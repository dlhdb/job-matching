"""讀取並驗證爬蟲輸出的職缺 JSON。"""

import json
from pathlib import Path
from typing import Any


def load_jobs(path: str | Path) -> list[dict[str, Any]]:
    """
    讀取爬蟲輸出的職缺 JSON。

    :param path: str or Path, 爬蟲輸出的 JSON 檔
    :return: list[dict], 依檔案順序排列的職缺
    :raises ValueError: 檔案不存在、格式錯誤、沒有職缺，或有職缺不是物件
    """
    path = Path(path)
    try:
        jobs = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"找不到職缺檔：{path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"職缺檔不是合法的 JSON：{path}（{e}）") from None

    if not isinstance(jobs, list) or not jobs:
        raise ValueError(f"職缺檔沒有任何職缺：{path}")
    if not all(isinstance(job, dict) for job in jobs):
        raise ValueError(f"職缺檔格式錯誤，每筆職缺都必須是物件：{path}")
    return jobs


def find_job(jobs: list[dict[str, Any]], job_no: str) -> dict[str, Any]:
    """
    依職缺代碼取出一筆職缺。

    :param jobs: list[dict], 職缺清單
    :param job_no: str, 職缺代碼
    :return: dict, 職缺資料
    :raises ValueError: 找不到指定的職缺代碼
    """
    for job in jobs:
        if str(job.get("職缺代碼")) == job_no:
            return job
    raise ValueError(f"職缺檔中找不到職缺代碼 {job_no}")
