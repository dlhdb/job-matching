"""工作評分需要網路的測試：把固定的測試職缺匯入測試資料庫，以 Gemini API 評所有還沒評分的職缺，並檢查寫入資料庫的結果。"""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

import score_job
from job_db import get_score_details, list_scored_jobs, open_db, save_run
from job_scoring.models import DIMENSIONS
from job_scoring.profile import load_preferences
from job_scoring.rules import check_hard_filters

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILE_DIR = DATA_DIR / "profile"
JOBS_FILE = DATA_DIR / "104" / "jobs.json"
# 測試資料庫放在專案內，方便跑完直接打開查看（output/ 不進版控）
E2E_DB = PROJECT_ROOT / "output" / "e2e" / "jobs.db"


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
    本模組開始前刪除上次留下的測試資料庫，再匯入測試職缺，每次都從沒有評分的資料庫開始；跑完保留，不刪除

    :return: Path, 測試資料庫路徑
    """
    # 先確認有 API key，沒有時整組跳過，不刪除上次的資料庫
    _require_api_key()
    E2E_DB.unlink(missing_ok=True)
    with closing(open_db(E2E_DB)) as conn:
        save_run(conn, _load_jobs(), datetime.now().replace(microsecond=0), "e2e")
    return E2E_DB


def _score_rows(db):
    """
    以職缺代碼為鍵取出 job_scores 表，同一筆職缺有多筆時取最新寫入的一筆

    :param db: Path, 資料庫檔
    :return: dict[str, dict]
    """
    with closing(sqlite3.connect(db)) as conn:
        cursor = conn.execute('SELECT * FROM job_scores ORDER BY "評分編號"')
        names = [d[0] for d in cursor.description]
        return {row["職缺代碼"]: row for row in (dict(zip(names, values)) for values in cursor)}


def _assert_scored_row(row):
    """
    確認沒被淘汰的職缺在 job_scores 中的列：評分明細的格式、各維度的分數與理由，以及總分、評語與評分明細中的值一致

    :param row: dict, job_scores 的一列
    """
    details = json.loads(row["評分明細"])
    assert list(details) == ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]
    assert list(details["維度"]) == list(DIMENSIONS)
    for name, dim in details["維度"].items():
        assert dim["理由"].strip(), f"{name} 沒有理由"
        assert dim["分數"] is None or 1 <= dim["分數"] <= 5
    assert 0 <= details["總分"] <= 100
    assert details["評語"]
    assert row["淘汰"] == 0
    assert row["總分"] == details["總分"]
    assert row["評語"] == details["評語"]
    assert (row["供應商"], row["模型"]) == ("gemini", "gemini-3.8-flash")


def _pick_job():
    """
    從測試職缺中挑出第一筆有工作內容、而且沒被淘汰的職缺

    :return: dict, 職缺
    """
    prefs = load_preferences(PROFILE_DIR / "preferences.yaml")
    for job in _load_jobs():
        if job.get("工作內容") and not check_hard_filters(job, prefs):
            return job
    pytest.fail(f"{JOBS_FILE.name} 中沒有「有工作內容且未被淘汰」的職缺")


@pytest.mark.network
def test_real_scoring(e2e_db, capsys):
    code = score_job.main(["--profile-dir", str(PROFILE_DIR), "--db", str(e2e_db)])
    captured = capsys.readouterr()
    job = _pick_job()
    job_no = str(job["職缺代碼"])
    with closing(open_db(e2e_db)) as conn:
        ranked = list_scored_jobs(conn, eliminated=False)
        data = get_score_details(conn, job_no)
    with capsys.disabled():
        print(f"\n{captured.err}")
        for r in ranked[:3]:
            print(f"{r['總分']:>3}｜{r['職缺名稱']}｜{r['公司名稱']}：{r['評語']}")
        print(f"\n職缺：{job['職缺名稱']}｜{job['公司名稱']}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[i] 資料庫：{e2e_db}")

    assert code == 0
    assert "評分完成" in captured.err
    # 挑出的那筆要評分成功，使用者才有理由可以閱讀
    assert data is not None and data["淘汰"] is False

    # 評分成功與被淘汰的職缺都有評分紀錄，評分失敗的職缺沒有
    prefs = load_preferences(PROFILE_DIR / "preferences.yaml")
    failed = {line.split()[1] for line in captured.err.splitlines() if line.startswith("[!] ")}
    rows = _score_rows(e2e_db)
    for job in _load_jobs():
        job_no = str(job["職缺代碼"])
        if job_no in failed:
            assert job_no not in rows
            continue
        row = rows[job_no]
        if check_hard_filters(job, prefs):
            assert row["淘汰"] == 1
            assert (row["總分"], row["供應商"], row["模型"]) == (None, None, None)
            assert json.loads(row["評分明細"])["淘汰原因"]
        else:
            _assert_scored_row(row)
