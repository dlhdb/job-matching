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
from job_db import open_db, save_run
from job_scoring.llm import LLMError
from job_scoring.models import AIAssessment
from job_scoring.settings import DEFAULTS, TEMPLATE, ScoringSettings, parse_preferences
from web import create_app

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
# 容器以 apt 裝的 Chromium；Playwright 預設只找自己下載的瀏覽器，要明確指定
CHROMIUM = Path("/usr/bin/chromium")


@pytest.fixture(autouse=True)
def isolate_db(tmp_path):
    """
    tmp_path 下的資料庫路徑；web app 與評分的測試都用它，不會寫入 data/jobs.db

    :return: Path, 資料庫的路徑（還沒建立）
    """
    return tmp_path / "jobs.db"


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
def web_app(isolate_db, frontend_dist):
    """
    live_server 提供的 app，測試可以直接操作它的狀態，例如在作業執行器放一個假作業

    :return: FastAPI
    """
    return create_app(isolate_db, frontend_dist)


@pytest.fixture
def live_server(web_app):
    """
    在測試行程的執行緒中起網頁伺服器（隨機 port），提供剛 build 好的前端，資料庫是 isolate_db

    資料在打開頁面前寫進 isolate_db 即可：每個請求各自開連線，讀得到最新的內容。
    伺服器和測試在同一個行程，monkeypatch 換掉的外部服務（例如 fake_104）也對它有效。

    :return: str, 伺服器的網址，例如 http://127.0.0.1:54321
    """
    config = uvicorn.Config(web_app, host="127.0.0.1", port=0, log_level="warning")
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
    以不等待的假函式取代爬蟲請求之間的延遲，並記錄每次的秒數，供驗證延遲範圍

    :return: list[float], 依呼叫順序記錄的延遲秒數
    """
    calls = []
    monkeypatch.setattr(fetch_104_jobs, "_sleep", lambda seconds, stop: calls.append(seconds))
    return calls


class FakeResponse:
    """模擬 requests.Response，只提供爬蟲會用到的屬性"""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class Hold:
    """讓假的 104 停在某個請求：reached 在請求進來時設定，release() 之後才回應"""

    def __init__(self):
        self.reached = threading.Event()
        self.released = threading.Event()

    def release(self):
        self.released.set()


class Fake104:
    """
    假的 104：依設定回應搜尋與取職缺頁面的請求，並記錄收到的請求

    沒設定的搜尋頁回傳空頁；取職缺頁面一律成功，除非代碼列在 failed_details。
    """

    SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
    DETAIL_URL = "https://www.104.com.tw/job/ajax/content/"

    def __init__(self):
        self.results = {}
        self.failed_details = set()
        self.searches = []
        self.details = []
        self._holds = {}
        self._lock = threading.Lock()

    def add(self, keyword, page, jobs, last_page):
        """
        設定某個關鍵字某一頁的搜尋結果

        :param jobs: list, 職缺代碼（產生預設內容）或完整的原始職缺 dict
        :param last_page: int, 回應中的最後一頁
        """
        self.results[(keyword, page)] = ([self.raw_job(j) if isinstance(j, str) else j for j in jobs], last_page)

    @staticmethod
    def raw_job(code, **overrides):
        """
        以職缺代碼產生搜尋 API 的原始職缺，職缺連結含這個代碼，取職缺頁面時對得回來

        :return: dict
        """
        job = {
            "jobNo": code,
            "jobName": f"職缺{code}",
            "custName": f"公司{code}",
            "coIndustryDesc": "軟體及網路相關業",
            "jobAddrNoDesc": "台北市大安區",
            "jobAddress": "",
            "salaryLow": 50000,
            "salaryHigh": 70000,
            "appearDate": "20260920",
            "applyCnt": 1,
            "pcSkills": [],
            "major": [],
            "tags": {},
            "link": {"job": f"//www.104.com.tw/job/{code}", "cust": f"//www.104.com.tw/company/c{code}"},
        }
        job.update(overrides)
        return job

    @staticmethod
    def description(code):
        """取職缺頁面成功時的工作內容"""
        return f"{code} 的完整工作內容"

    def hold(self, kind, n):
        """
        讓第 n 個搜尋（kind="search"）或取職缺頁面（kind="detail"）的請求停住，n 從 1 開始

        :return: Hold
        """
        gate = Hold()
        self._holds[(kind, n)] = gate
        return gate

    def release_all(self):
        for gate in self._holds.values():
            gate.release()

    def get(self, url, params=None, headers=None, timeout=None):
        with self._lock:
            if url.startswith(self.DETAIL_URL):
                kind, code = "detail", url[len(self.DETAIL_URL):]
                self.details.append(code)
                n = len(self.details)
            else:
                assert url == self.SEARCH_URL
                kind = "search"
                self.searches.append((params.get("keyword"), params["page"], params.get("area"), params["ro"]))
                n = len(self.searches)
        gate = self._holds.get((kind, n))
        if gate is not None:
            gate.reached.set()
            gate.released.wait(timeout=30)
        if kind == "detail":
            if code in self.failed_details:
                return FakeResponse(500)
            return FakeResponse(200, {"data": {"jobDetail": {
                "jobDescription": self.description(code), "salary": "月薪50,000~70,000元",
            }}})
        keyword, page = params.get("keyword"), params["page"]
        if (keyword, page) not in self.results:
            return FakeResponse(200, {"data": [], "metadata": {}})
        jobs, last_page = self.results[(keyword, page)]
        return FakeResponse(200, {"data": jobs, "metadata": {"pagination": {"lastPage": last_page}}})


@pytest.fixture
def fake_104(monkeypatch, no_sleep):
    """
    以假的 104 取代爬蟲的 requests.get，請求之間不等待；結束時放行所有停住的請求

    :return: Fake104
    """
    fake = Fake104()
    monkeypatch.setattr(fetch_104_jobs.requests, "get", fake.get)
    yield fake
    fake.release_all()


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
def prefs(preferences_data):
    """
    共用測試偏好

    :return: Preferences
    """
    return parse_preferences(yaml.safe_dump(preferences_data, allow_unicode=True))


# 共用測試設定的版本號：偏好第 2 版、經歷第 3 版、模板第 1 版，三個都不同才分得出寫錯欄
TEST_VERSIONS = {"preferences": 2, "experience": 3, "template": 1}


@pytest.fixture
def scoring_settings(prefs):
    """
    共用測試設定：測試偏好、經歷「經歷標記-BBB」、預設模板

    :return: ScoringSettings
    """
    return ScoringSettings(
        preferences=prefs, experience="經歷標記-BBB", template=DEFAULTS[TEMPLATE], versions=dict(TEST_VERSIONS),
    )


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
    isolate_db 的資料庫，已寫入 ok、out 兩筆職缺，還沒有任何評分

    :return: Path, 資料庫路徑
    """
    with closing(open_db(isolate_db)) as conn:
        save_run(conn, [ok_job, out_job], datetime(2026, 9, 1, 10, 0, 0), "爬蟲")
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
