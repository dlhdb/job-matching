"""工作評分需要網路的測試：把固定的測試職缺寫進測試資料庫，經由網頁的 API 送去評分（Gemini），並印出 AI 給的理由供使用者閱讀。"""

import json
import os
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from fastapi.testclient import TestClient

from job_db import list_scores, open_db, save_run
from job_scoring.llm import DEFAULT_MODEL
from job_scoring.models import DIMENSIONS
from job_scoring.rules import check_hard_filters
from job_scoring.settings import parse_preferences
from web import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILE_DIR = DATA_DIR / "profile"
JOBS_FILE = DATA_DIR / "104" / "jobs.json"
# 測試資料庫放在專案內，方便跑完直接打開查看（output/ 不進版控）
E2E_DB = PROJECT_ROOT / "output" / "e2e" / "jobs.db"


def _profile(name):
    """
    e2e 的固定設定：擬真的偏好與經歷（測試資料，不是使用者的設定）；模板用預設模板

    :param name: str, tests/e2e/data/profile/ 下的檔名
    :return: str, 檔案內容
    """
    return (PROFILE_DIR / name).read_text(encoding="utf-8")


def _require_api_key():
    """從 .env 載入 API key，沒有設定時呼叫 pytest.skip"""
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("尚未在 .env 設定 GEMINI_API_KEY")


def _load_jobs():
    """
    讀取固定的測試職缺

    :return: list[dict]
    """
    return json.loads(JOBS_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def e2e_db():
    """
    本模組開始前刪除上次留下的測試資料庫，再寫入測試職缺，每次都從沒有評分的資料庫開始；跑完保留，不刪除

    :return: Path, 測試資料庫路徑
    """
    # 先確認有 API key，沒有時整組跳過，不刪除上次的資料庫
    _require_api_key()
    E2E_DB.unlink(missing_ok=True)
    with closing(open_db(E2E_DB)) as conn:
        save_run(conn, _load_jobs(), datetime.now().replace(microsecond=0), "e2e")
    return E2E_DB


def _assert_scored(details, record):
    """
    確認評分成功的職缺：評分明細的格式、各維度的分數與理由，以及評分紀錄的供應商與模型

    :param details: dict | None, 評分明細
    :param record: dict | None, 評分紀錄
    """
    assert details is not None and details["淘汰"] is False
    assert list(details) == ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]
    assert list(details["維度"]) == list(DIMENSIONS)
    for name, dim in details["維度"].items():
        assert dim["理由"].strip(), f"{name} 沒有理由"
        assert dim["分數"] is None or 1 <= dim["分數"] <= 5
    assert 0 <= details["總分"] <= 100
    assert details["評語"]
    assert record is not None
    assert (record["供應商"], record["模型"]) == ("gemini", "gemini-3.8-flash")


def _pick_jobs():
    """
    從測試職缺中挑出所有有工作內容、而且沒被淘汰的職缺

    :return: list[dict], 職缺
    """
    prefs = parse_preferences(_profile("preferences.yaml"))
    jobs = [job for job in _load_jobs() if job.get("工作內容") and not check_hard_filters(job, prefs)]
    if not jobs:
        pytest.fail(f"{JOBS_FILE.name} 中沒有「有工作內容且未被淘汰」的職缺")
    return jobs


def _score_via_api(db_path, codes):
    """
    以網頁的 API 存入 e2e 的偏好與經歷，送去評分並等到評完

    :param db_path: Path, 測試資料庫路徑
    :param codes: list[str], 送去評分的職缺代碼
    :return: dict, 結束時的 RunOut
    """
    with TestClient(create_app(db_path)) as client:
        for kind, name in (("preferences", "preferences.yaml"), ("experience", "experience.md")):
            response = client.post(
                f"/api/settings/{kind}/versions", json={"name": "e2e", "description": "", "content": _profile(name)},
            )
            assert response.status_code == 201, response.text
        response = client.post("/api/scoring", json={"codes": codes, "rescore": False, "model": DEFAULT_MODEL})
        assert response.status_code == 202, response.text
        while (state := client.get("/api/scoring").json())["running"] is not None:
            time.sleep(1)
        return state["last"]


@pytest.mark.network
def test_ai_scoring(e2e_db):
    run = _score_via_api(e2e_db, [str(job["職缺代碼"]) for job in _load_jobs()])
    with closing(open_db(e2e_db)) as conn:
        scored = [(job, list_scores(conn, str(job["職缺代碼"]))) for job in _pick_jobs()]

    print(f"\n[i] 成功 {run['ok']}、淘汰 {run['eliminated']}、失敗 {run['failed']}")
    for status in run["statuses"]:
        print(f"[!] {status['code']}：{status['reason']}")
    for job, records in scored:
        print(f"\n職缺：{job['職缺名稱']}｜{job['公司名稱']}")
        print(json.dumps(records[0]["評分明細"] if records else None, ensure_ascii=False, indent=2))
    print(f"[i] 資料庫：{e2e_db}")

    assert run["error"] is None
    # 這些職缺都要評分成功，使用者才有理由可以閱讀
    for _, records in scored:
        _assert_scored(records[0]["評分明細"] if records else None, records[0] if records else None)
