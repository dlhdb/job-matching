"""pytest 共用 fixture。"""

import pytest

import fetch_104_jobs


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
