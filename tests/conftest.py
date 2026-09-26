"""pytest 共用 fixture。"""

import copy
import shutil
import subprocess
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
import uvicorn
import yaml

import fetch_104_jobs
import score_job as score_job_cli
from job_db import open_db, save_run
from job_scoring.llm import LLMError
from job_scoring.models import AIAssessment
from job_scoring.profile import load_preferences
from web import create_app

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
# 容器以 apt 裝的 Chromium；Playwright 預設只找自己下載的瀏覽器，要明確指定
CHROMIUM = Path("/usr/bin/chromium")


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """
    把評分 CLI 的預設資料庫指到 tmp_path，沒有指定 --db 的測試也不會寫入 data/jobs.db

    :return: Path, 預設資料庫的路徑
    """
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(score_job_cli, "DEFAULT_DB_PATH", path)
    return path


@pytest.fixture
def db_conn(tmp_path):
    """
    tmp_path 下已初始化的資料庫連線（與 isolate_db 是同一個檔案）

    :return: sqlite3.Connection
    """
    connection = open_db(tmp_path / "jobs.db")
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def frontend_dist():
    """
    整個測試過程 build 一次前端，瀏覽器測試才不會拿到改前端之前的舊 build

    沒有 npm 或還沒安裝前端依賴時 skip；build 失敗時讓測試失敗並附上輸出。

    :return: Path, build 好的前端目錄
    """
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("找不到 npm，無法 build 前端")
    if not (FRONTEND_DIR / "node_modules" / ".bin").is_dir():
        pytest.skip("還沒安裝前端依賴，先執行 npm ci --prefix frontend")
    result = subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"前端 build 失敗：\n{result.stdout}{result.stderr}")
    return FRONTEND_DIR / "dist"


@pytest.fixture
def live_server(isolate_db, frontend_dist):
    """
    在測試行程的執行緒中起網頁伺服器（隨機 port），提供剛 build 好的前端，資料庫是 isolate_db

    資料在打開頁面前寫進 isolate_db 即可：每個請求各自開連線，讀得到最新的內容。

    :return: str, 伺服器的網址，例如 http://127.0.0.1:54321
    """
    config = uvicorn.Config(create_app(isolate_db, frontend_dist), host="127.0.0.1", port=0,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            pytest.fail("網頁伺服器沒有啟動")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """
    覆寫 pytest-playwright 的同名 fixture，改用系統的 Chromium；找不到時 skip

    :return: dict, 啟動瀏覽器的參數
    """
    if not CHROMIUM.is_file():
        pytest.skip(f"找不到 {CHROMIUM}，瀏覽器測試要在 devcontainer 內執行")
    return {**browser_type_launch_args, "executable_path": str(CHROMIUM)}


@pytest.fixture
def no_sleep(monkeypatch):
    """
    以不等待的假函式取代 time.sleep，並記錄每次呼叫的秒數，供驗證延遲範圍

    :return: list[float], 依呼叫順序記錄的延遲秒數
    """
    calls = []
    monkeypatch.setattr(fetch_104_jobs.time, "sleep", calls.append)
    return calls


@pytest.fixture
def make_raw_job():
    """
    產生 104 搜尋 API 回傳的單筆原始職缺，可用關鍵字參數覆寫欄位

    :return: callable, make_raw_job(**overrides) -> dict
    """
    def _make(**overrides):
        job = {
            "jobNo": "1",
            "jobName": "Python 工程師",
            "custName": "甲公司",
            "coIndustryDesc": "軟體及網路相關業",
            "jobAddrNoDesc": "台北市大安區",
            "jobAddress": "",
            "salaryLow": 60000,
            "salaryHigh": 80000,
            "appearDate": "20260521",
            "applyCnt": 3,
            "description": "搜尋摘要片段",
            "pcSkills": [{"description": "Python"}, {"description": "Git"}],
            "major": ["資訊工程相關"],
            "tags": {"remote": {"desc": "遠端工作"}},
            "link": {
                "job": "//www.104.com.tw/job/8s12x?jobsource=search",
                "cust": "//www.104.com.tw/company/abc",
            },
        }
        job.update(overrides)
        return job
    return _make


# ---------------------------------------------------------------------------
# 工作評分的共用測試資料
# ---------------------------------------------------------------------------

# 共用測試偏好（完整的偏好檔內容）
TEST_PREFERENCES = {
    "目標方向": ["目標標記-AAA"],
    "產業偏好": {"喜歡": ["軟體及網路相關業", "金融科技"], "不喜歡": ["博弈"]},
    "薪資": {"期望月薪": 70000, "底線月薪": 55000, "年薪換算月數": 14},
    "淘汰條件": {"公司": ["乙公司"], "職稱關鍵字": ["業務"]},
    "權重": {"職涯方向契合度": 0.4, "技能匹配度": 0.25, "產業公司吸引力": 0.15, "薪資水準": 0.2},
}


@pytest.fixture
def preferences_data():
    """
    共用測試偏好的副本（可在測試中修改）

    :return: dict, 偏好檔內容
    """
    return copy.deepcopy(TEST_PREFERENCES)


@pytest.fixture
def write_profile(tmp_path):
    """
    把偏好 dict 與經歷寫到 tmp_path 下的 profile 目錄

    :return: callable, write_profile(preferences: dict) -> Path（profile 目錄）
    """
    def _write(preferences):
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir(exist_ok=True)
        (profile_dir / "preferences.yaml").write_text(
            yaml.safe_dump(preferences, allow_unicode=True), encoding="utf-8")
        (profile_dir / "experience.md").write_text("經歷標記-BBB", encoding="utf-8")
        return profile_dir
    return _write


@pytest.fixture
def profile_dir(write_profile, preferences_data):
    """
    寫好共用測試偏好與經歷的 profile 目錄

    :return: Path, profile 目錄
    """
    return write_profile(preferences_data)


@pytest.fixture
def prefs(profile_dir):
    """
    載入共用測試偏好

    :return: Preferences
    """
    return load_preferences(profile_dir / "preferences.yaml")


@pytest.fixture
def make_job():
    """
    產生爬蟲輸出格式的單筆職缺（共用欄位），可用關鍵字參數覆寫中文欄位

    :return: callable, make_job(**overrides) -> dict
    """
    def _make(**overrides):
        job = {
            "職缺代碼": "ok",
            "職缺名稱": "Python 工程師",
            "公司名稱": "甲公司",
            "產業類別": "軟體及網路相關業",
            "地區": "台北市大安區",
            "薪資待遇": "月薪60,000~80,000元",
            "薪資下限": 60000,
            "薪資上限": 80000,
            "更新日期": "2026-09-01",
            "應徵人數": 3,
            "工作內容": "工作標記-CCC",
            "電腦專長": "",
            "科系要求": "",
            "特色標籤": "",
            "職缺連結": "https://www.104.com.tw/job/ok",
            "公司連結": "https://www.104.com.tw/company/abc",
        }
        job.update(overrides)
        return job
    return _make


@pytest.fixture
def ok_job(make_job):
    """不會被淘汰的職缺"""
    return make_job()


@pytest.fixture
def out_job(make_job):
    """職稱含「業務」、會被淘汰的職缺"""
    return make_job(**{"職缺代碼": "out", "職缺名稱": "業務專員"})


@pytest.fixture
def jobs_db(isolate_db, ok_job, out_job):
    """
    評分 CLI 預設的資料庫（isolate_db），已寫入 ok、out 兩筆職缺，還沒有任何評分

    :return: Path, 資料庫路徑
    """
    with closing(open_db(isolate_db)) as conn:
        save_run(conn, [ok_job, out_job], datetime(2026, 9, 1, 10, 0, 0), "匯入")
    return isolate_db


def make_assessment(career=5, skill=None, industry=3, comment="總評"):
    """
    產生固定內容的 AIAssessment

    :return: AIAssessment
    """
    return AIAssessment.model_validate({
        "career_fit": {"score": career, "reason": "職涯理由"},
        "skill_match": {"score": skill, "reason": "技能理由"},
        "industry_fit": {"score": industry, "reason": "產業理由"},
        "comment": comment,
    })


class FakeLLMClient:
    """不連網的假 LLM client，回傳固定的 AIAssessment 並記錄呼叫"""

    def __init__(self, assessment):
        self.assessment = assessment
        self.calls = []

    def assess(self, system, user):
        self.calls.append((system, user))
        return self.assessment


@pytest.fixture
def make_client():
    """
    產生假的 LLM client，可指定三個 AI 維度的分數與總評

    :return: callable, make_client(career=5, skill=None, industry=3, comment="總評") -> FakeLLMClient
    """
    def _make(**kwargs):
        return FakeLLMClient(make_assessment(**kwargs))
    return _make


@pytest.fixture
def fake_client(make_client):
    """
    假的 LLM client：career_fit 5、skill_match null、industry_fit 3、總評為「總評」

    :return: FakeLLMClient, 以 len(client.calls) 取得呼叫次數
    """
    return make_client()


class BatchFakeLLMClient:
    """
    整批用的假 LLM client：依 user 提示詞中的職缺名稱決定行為

    behaviors 的值可以是 dict（make_assessment 的參數）、"llm_error"（拋出 LLMError）
    或 "invalid"（以 6 分驗證，拋出 ValidationError）；沒列到的職缺回傳預設的 make_assessment()
    """

    def __init__(self, behaviors):
        self.behaviors = behaviors
        self.calls = []

    def assess(self, system, user):
        name = next((n for n in self.behaviors if n in user), None)
        self.calls.append(name)
        behavior = self.behaviors.get(name, {})
        if behavior == "llm_error":
            raise LLMError("模擬的 API 錯誤")
        if behavior == "invalid":
            return make_assessment(career=6)
        return make_assessment(**behavior)


@pytest.fixture
def make_batch_client():
    """
    產生整批用的假 LLM client

    :return: callable, make_batch_client(behaviors: dict) -> BatchFakeLLMClient
    """
    return BatchFakeLLMClient


@pytest.fixture
def forbid_client(monkeypatch):
    """
    禁止建立 LLM client：score_job.get_client 一被呼叫就讓測試失敗，並把 GEMINI_API_KEY 設為空字串

    :return: list, 呼叫紀錄（正常情況應保持空清單）
    """
    calls = []

    def _forbidden(*args, **kwargs):
        calls.append(args)
        pytest.fail("不應建立 LLM client")

    monkeypatch.setattr(score_job_cli, "get_client", _forbidden)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    return calls
