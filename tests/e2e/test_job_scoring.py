"""工作評分需要網路的測試：以固定的測試資料與 Gemini API 評分單筆與整批職缺，並檢查寫入資料庫的結果。"""

import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from dotenv import load_dotenv

import score_job
from job_scoring.models import DIMENSIONS
from job_scoring.profile import load_preferences
from job_scoring.rules import check_hard_filters

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILE_DIR = DATA_DIR / "profile"
JOBS_FILE = DATA_DIR / "104" / "jobs.json"
# 單筆與整批共用的測試資料庫，放在專案內方便跑完直接打開查看（output/ 不進版控）
E2E_DB = PROJECT_ROOT / "output" / "e2e" / "jobs.db"


def _require_api_key():
    """從 .env 載入 API key，沒有設定時呼叫 pytest.skip"""
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("尚未在 .env 設定 GEMINI_API_KEY")


@pytest.fixture(scope="module")
def e2e_db():
    """
    本模組開始前刪除上次留下的測試資料庫，讓每次都從空的資料庫開始；跑完保留，不刪除

    :return: Path, 測試資料庫路徑
    """
    # 先確認有 API key，沒有時整組跳過，不刪除上次的資料庫
    _require_api_key()
    E2E_DB.unlink(missing_ok=True)
    return E2E_DB


def _score_rows(db):
    """
    以職缺代碼為鍵取出 job_scores 表

    :param db: Path, 資料庫檔
    :return: dict[str, dict]
    """
    with closing(sqlite3.connect(db)) as conn:
        cursor = conn.execute("SELECT * FROM job_scores")
        names = [d[0] for d in cursor.description]
        return {row[0]: dict(zip(names, row)) for row in cursor}


def _assert_scored_row(row, data):
    """
    確認沒被淘汰的職缺在 job_scores 中的列與輸出的評分結果一致

    :param row: dict, job_scores 的一列
    :param data: dict, 輸出的評分結果（中文鍵名）
    """
    assert json.loads(row["評分結果"]) == data
    assert row["淘汰"] == 0
    assert row["總分"] == data["總分"]
    assert row["評語"] == data["評語"]
    assert re.fullmatch(r"[0-9a-f]{64}", row["快取鍵"])
    assert (row["供應商"], row["模型"]) == ("gemini", "gemini-3.8-flash")


def _pick_job():
    """
    從測試職缺中挑出第一筆有工作內容、而且沒被淘汰的職缺

    :return: dict, 職缺
    """
    prefs = load_preferences(PROFILE_DIR / "preferences.yaml")
    for job in json.loads(JOBS_FILE.read_text(encoding="utf-8")):
        if job.get("工作內容") and not check_hard_filters(job, prefs):
            return job
    pytest.fail(f"{JOBS_FILE.name} 中沒有「有工作內容且未被淘汰」的職缺")


@pytest.mark.network
def test_real_scoring(e2e_db, capsys):
    job = _pick_job()

    code = score_job.main(["--jobs", str(JOBS_FILE), "--profile-dir", str(PROFILE_DIR),
                           "--job-no", str(job["職缺代碼"]), "--db", str(e2e_db)])
    captured = capsys.readouterr()
    with capsys.disabled():
        print(f"\n職缺：{job['職缺名稱']}｜{job['公司名稱']}")
        print(captured.out)
        print(captured.err)
        print(f"[i] 資料庫：{e2e_db}")

    assert code == 0
    data = json.loads(captured.out)
    assert list(data) == ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]
    assert data["淘汰"] is False
    assert list(data["維度"]) == list(DIMENSIONS)
    for name, dim in data["維度"].items():
        assert dim["理由"].strip(), f"{name} 沒有理由"
        assert dim["分數"] is None or 1 <= dim["分數"] <= 5
    assert 0 <= data["總分"] <= 100
    assert data["評語"]

    _assert_scored_row(_score_rows(e2e_db)[job["職缺代碼"]], data)


@pytest.mark.network
def test_real_batch_scoring(e2e_db, tmp_path, monkeypatch, capsys):
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    monkeypatch.setattr(score_job, "SCORES_DIR", tmp_path / "scores")

    code = score_job.main(["--jobs", str(JOBS_FILE), "--profile-dir", str(PROFILE_DIR), "--db", str(e2e_db)])
    captured = capsys.readouterr()
    records = json.loads((tmp_path / "scores" / f"{JOBS_FILE.stem}_scored.json").read_text(encoding="utf-8"))
    with capsys.disabled():
        print(f"\n{captured.err}")
        ranked = sorted((r for r in records if r["總分"] is not None), key=lambda r: r["總分"], reverse=True)
        for r in ranked[:3]:
            print(f"{r['總分']:>3}｜{r['職缺名稱']}｜{r['公司名稱']}：{r['評語']}")
        print(f"[i] 資料庫：{e2e_db}")

    assert code == 0
    assert len(records) == len(jobs) == 5

    # 評分成功與被淘汰的職缺各有一列，內容與結果檔一致。
    # 資料庫與單筆評分共用，評分失敗的職缺可能留有單筆評分的列，因此不檢查（失敗不寫入由離線測試驗證）
    rows = _score_rows(e2e_db)
    for record in records:
        if record["失敗原因"] is not None:
            continue
        row = rows[record["職缺代碼"]]
        if record["淘汰"]:
            assert row["淘汰"] == 1
            assert (row["總分"], row["快取鍵"], row["供應商"], row["模型"]) == (None, None, None, None)
            assert json.loads(row["評分結果"])["淘汰原因"] == record["淘汰原因"]
        else:
            data = {k: v for k, v in record.items() if k not in ("職缺名稱", "公司名稱", "薪資待遇", "職缺連結", "失敗原因")}
            _assert_scored_row(row, data)
