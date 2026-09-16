"""pytest 共用 fixture。"""

import copy
import json
from pathlib import Path

import pytest
import yaml

import fetch_104_jobs
import score_job as score_job_cli
from job_scoring.models import AIAssessment
from job_scoring.profile import load_preferences

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
# 工作評分（F1-01）的共用測試資料，見 PRD §6「共用測試資料」
# ---------------------------------------------------------------------------

# 覆寫範本 preferences.example.yaml 的欄位
TEST_PREFERENCES = {
    "目標方向": ["目標標記-AAA"],
    "薪資": {"期望月薪": 70000, "底線月薪": 55000, "年薪換算月數": 14},
    "淘汰條件": {"公司": ["乙公司"], "職稱關鍵字": ["業務"]},
    "權重": {"職涯方向契合度": 0.4, "技能匹配度": 0.25, "產業公司吸引力": 0.15, "薪資水準": 0.2},
}


@pytest.fixture
def preferences_data():
    """
    以 profile/preferences.example.yaml 為基礎、覆寫測試欄位後的偏好 dict（可在測試中再修改）

    :return: dict, 偏好檔內容
    """
    example = PROJECT_ROOT / "profile" / "preferences.example.yaml"
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    data.update(copy.deepcopy(TEST_PREFERENCES))
    return data


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
def jobs_file(tmp_path, ok_job, out_job):
    """
    含 ok、out 兩筆職缺的爬蟲輸出 JSON

    :return: Path, JSON 檔路徑
    """
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([ok_job, out_job], ensure_ascii=False), encoding="utf-8")
    return path


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
