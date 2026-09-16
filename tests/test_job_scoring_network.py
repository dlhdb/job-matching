"""工作評分（F1-01）需要網路的測試（AC-8）：以真實個人資料與 Gemini API 評分一筆職缺。"""

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

import score_job
from job_scoring.models import DIMENSIONS
from job_scoring.profile import load_preferences
from job_scoring.rules import check_hard_filters

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = PROJECT_ROOT / "profile"
OUTPUT_DIR = PROJECT_ROOT / "output" / "104"


def _pick_job():
    """
    從最新一份爬蟲結果中，挑出第一筆有工作內容、而且沒被淘汰的職缺

    :return: tuple (Path, dict), (職缺檔, 職缺)；缺少前提時呼叫 pytest.skip
    """
    for name in ("preferences.yaml", "experience.md"):
        if not (PROFILE_DIR / name).is_file():
            pytest.skip(f"尚未建立 profile/{name}")
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("尚未在 .env 設定 GEMINI_API_KEY")

    files = sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        pytest.skip("output/104/ 中沒有爬蟲結果，請先執行 fetch_104_jobs.py")
    latest = files[-1]

    prefs = load_preferences(PROFILE_DIR / "preferences.yaml")
    for job in json.loads(latest.read_text(encoding="utf-8")):
        if job.get("工作內容") and not check_hard_filters(job, prefs):
            return latest, job
    pytest.skip(f"{latest.name} 中沒有「有工作內容且未被淘汰」的職缺")


@pytest.mark.network
def test_real_scoring(capsys):
    jobs_file, job = _pick_job()

    code = score_job.main(["--jobs", str(jobs_file), "--job-no", str(job["職缺代碼"])])
    captured = capsys.readouterr()
    with capsys.disabled():
        print(f"\n職缺：{job['職缺名稱']}｜{job['公司名稱']}（{jobs_file.name}）")
        print(captured.out)
        print(captured.err)

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
