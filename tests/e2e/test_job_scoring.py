"""工作評分需要網路的測試：把固定的測試職缺寫進測試資料庫，以 Gemini API 評所有職缺，並印出 AI 給的理由供使用者閱讀。"""

import json
import os
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from job_db import get_score_details, list_scores, open_db, save_run
from job_scoring.batch import score_batch
from job_scoring.llm import DEFAULT_MODEL, DEFAULT_PROVIDER, get_client
from job_scoring.models import DIMENSIONS
from job_scoring.rules import check_hard_filters
from job_scoring.settings import DEFAULTS, TEMPLATE, ScoringSettings, parse_preferences

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILE_DIR = DATA_DIR / "profile"
JOBS_FILE = DATA_DIR / "104" / "jobs.json"
# 測試資料庫放在專案內，方便跑完直接打開查看（output/ 不進版控）
E2E_DB = PROJECT_ROOT / "output" / "e2e" / "jobs.db"


def _settings():
    """
    e2e 的固定設定：擬真的偏好與經歷（測試資料，不是使用者的設定），加上預設模板

    :return: ScoringSettings
    """
    return ScoringSettings(
        preferences=parse_preferences((PROFILE_DIR / "preferences.yaml").read_text(encoding="utf-8")),
        experience=(PROFILE_DIR / "experience.md").read_text(encoding="utf-8"),
        template=DEFAULTS[TEMPLATE],
        versions={"preferences": 1, "experience": 1, "template": 1},
    )


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
    prefs = _settings().preferences
    jobs = [job for job in _load_jobs() if job.get("工作內容") and not check_hard_filters(job, prefs)]
    if not jobs:
        pytest.fail(f"{JOBS_FILE.name} 中沒有「有工作內容且未被淘汰」的職缺")
    return jobs


@pytest.mark.network
def test_ai_scoring(e2e_db):
    progress = []
    with closing(open_db(e2e_db)) as conn:
        results = score_batch(
            _load_jobs(), _settings(), lambda: get_client(DEFAULT_PROVIDER, DEFAULT_MODEL), progress.append,
            conn=conn, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL,
        )
        jobs = _pick_jobs()
        scored = [
            (job, get_score_details(conn, str(job["職缺代碼"])), list_scores(conn, str(job["職缺代碼"])))
            for job in jobs
        ]

    print("\n" + "\n".join(progress))
    for result in results:
        if result.failure:
            print(f"[!] {result.job_no} {result.job_name}：{result.failure}")
    for job, data, _ in scored:
        print(f"\n職缺：{job['職缺名稱']}｜{job['公司名稱']}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"[i] 資料庫：{e2e_db}")

    # 這些職缺都要評分成功，使用者才有理由可以閱讀
    for _, data, records in scored:
        _assert_scored(data, records[0] if records else None)
