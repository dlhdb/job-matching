"""104 職缺爬蟲的離線測試。HTTP 請求與請求之間的延遲一律以 monkeypatch 取代。"""

import threading
from datetime import datetime

import pytest
import requests

import fetch_104_jobs as m
from job_db import JOB_COLUMNS

DETAIL = {
    "jobDescription": "完整工作內容",
    "salary": "月薪60,000~80,000元",
    "salaryType": 50,
    "salaryMin": 60000,
    "salaryMax": 80000,
}


class FakeResponse:
    """模擬 requests.Response，只提供爬蟲會用到的屬性"""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def fake_get(monkeypatch):
    """
    以假函式取代 requests.get，記錄每次呼叫的參數

    :return: callable, fake_get(response_or_exception) -> list[dict]（呼叫紀錄）
    """
    def _install(result):
        calls = []

        def _get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(m.requests, "get", _get)
        return calls
    return _install


# ---------------------------------------------------------------------------
# 通用工具函式
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("20260521", "2026-05-21"),
    ("", ""),
    (None, ""),
    ("2026/05/21", "2026/05/21"),  # 格式不符時原樣回傳
])
def test_format_date(raw, expected):
    assert m.format_date(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("//www.104.com.tw/job/8s12x", "https://www.104.com.tw/job/8s12x"),
    ("https://www.104.com.tw/job/8s12x", "https://www.104.com.tw/job/8s12x"),
    ("", ""),
])
def test_normalize_url(raw, expected):
    assert m._normalize_url(raw) == expected


@pytest.mark.parametrize("url, expected", [
    ("https://www.104.com.tw/job/8s12x", "8s12x"),
    ("https://www.104.com.tw/job/8s12x?jobsource=search", "8s12x"),
    ("https://www.104.com.tw/job/8s12x/", "8s12x"),
    ("https://www.104.com.tw/company/abc", None),
    ("", None),
])
def test_extract_job_id(url, expected):
    assert m._extract_job_id(url) == expected


def test_extract_tag_descriptions_skips_empty_and_invalid():
    tags = {"a": {"desc": "遠端工作"}, "b": {"desc": ""}, "c": {}, "d": "不是 dict"}
    assert m._extract_tag_descriptions(tags) == ["遠端工作"]


@pytest.mark.parametrize("tags", [None, [], "字串"])
def test_extract_tag_descriptions_non_dict(tags):
    assert m._extract_tag_descriptions(tags) == []


def test_extract_skill_descriptions_skips_empty_and_invalid():
    skills = [{"description": "Python"}, {"description": ""}, {}, "不是 dict"]
    assert m._extract_skill_descriptions(skills) == ["Python"]


@pytest.mark.parametrize("skills", [None, {}, "字串"])
def test_extract_skill_descriptions_non_list(skills):
    assert m._extract_skill_descriptions(skills) == []


@pytest.mark.parametrize("raw, expected", [
    ("Python, React，AI", ["Python", "React", "AI"]),
    ("Python,React, Python", ["Python", "React"]),
    ("  Python  ", ["Python"]),
    ("", []),
    (",，, ", []),
])
def test_parse_keywords(raw, expected):
    assert m.parse_keywords(raw) == expected


def test_areas_lists_22_cities():
    assert len(m.AREAS) == 22
    assert m.AREAS["新竹縣"] == "6001007000"
    assert m.AREAS["新竹市"] == "6001006000"


# ---------------------------------------------------------------------------
# API 請求函式
# ---------------------------------------------------------------------------

def test_fetch_jobs_success_sends_headers_params_and_timeout(fake_get):
    payload = {"data": [{"jobNo": "1"}], "metadata": {"pagination": {"lastPage": 3}}}
    calls = fake_get(FakeResponse(200, payload))

    jobs, pagination = m.fetch_jobs("Python", page=2, area_code="6001001000", ro=1)

    assert jobs == [{"jobNo": "1"}]
    assert pagination == {"lastPage": 3}
    (call,) = calls
    assert call["url"] == "https://www.104.com.tw/jobs/search/api/jobs"
    assert call["headers"] == m.DEFAULT_HEADERS
    assert {"User-Agent", "Referer"} <= set(call["headers"])
    assert call["timeout"]
    assert call["params"] == {
        "page": 2, "mode": "s", "ro": 1, "keyword": "Python", "area": "6001001000",
    }


def test_fetch_jobs_omits_empty_keyword_and_area(fake_get):
    calls = fake_get(FakeResponse(200, {}))

    assert m.fetch_jobs("") == ([], {})
    assert calls[0]["params"] == {"page": 1, "mode": "s", "ro": 0}


def test_fetch_jobs_http_error(fake_get, capsys):
    fake_get(FakeResponse(403))

    assert m.fetch_jobs("Python") == ([], {})
    assert "[-]" in capsys.readouterr().out


def test_fetch_jobs_request_exception(fake_get, capsys):
    fake_get(requests.exceptions.ConnectionError("連線失敗"))

    assert m.fetch_jobs("Python") == ([], {})
    assert "[-]" in capsys.readouterr().out


def test_fetch_job_detail_success_uses_job_referer(fake_get):
    original_headers = dict(m.DEFAULT_HEADERS)
    calls = fake_get(FakeResponse(200, {"data": {"jobDetail": {**DETAIL, "other": "x"}}}))

    assert m.fetch_job_detail("8s12x") == DETAIL

    (call,) = calls
    assert call["url"] == "https://www.104.com.tw/job/ajax/content/8s12x"
    assert call["headers"]["Referer"] == "https://www.104.com.tw/job/8s12x"
    assert call["headers"]["User-Agent"] == m.DEFAULT_HEADERS["User-Agent"]
    assert call["timeout"]
    assert m.DEFAULT_HEADERS == original_headers  # 不可改到共用的標頭


def test_fetch_job_detail_http_error(fake_get):
    fake_get(FakeResponse(404))
    assert m.fetch_job_detail("8s12x") is None


def test_fetch_job_detail_exception(fake_get, capsys):
    fake_get(requests.exceptions.Timeout("逾時"))

    assert m.fetch_job_detail("8s12x") is None
    assert "[!]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 欄位整理
# ---------------------------------------------------------------------------

def test_parse_job_with_detail(make_raw_job):
    job = m.parse_job(make_raw_job(), dict(DETAIL))

    assert job == {
        "職缺代碼": "1",
        "職缺名稱": "Python 工程師",
        "公司名稱": "甲公司",
        "產業類別": "軟體及網路相關業",
        "地區": "台北市大安區",
        "薪資待遇": "月薪60,000~80,000元",
        "薪資下限": 60000,
        "薪資上限": 80000,
        "更新日期": "2026-05-21",
        "應徵人數": 3,
        "工作內容": "完整工作內容",
        "電腦專長": "Python, Git",
        "科系要求": "資訊工程相關",
        "特色標籤": "遠端工作",
        "職缺連結": "https://www.104.com.tw/job/8s12x?jobsource=search",
        "公司連結": "https://www.104.com.tw/company/abc",
    }


def test_parse_job_matches_job_columns(make_raw_job):
    # 本功能輸出的欄名與順序對齊契約的實作 JOB_COLUMNS，不是反過來
    assert list(m.parse_job(make_raw_job(), None)) == [name for name, _ in JOB_COLUMNS]
    assert list(m.parse_job({}, None)) == [name for name, _ in JOB_COLUMNS]


def test_parse_job_detail_failure_does_not_backfill(make_raw_job):
    job = m.parse_job(make_raw_job(), None)

    # 搜尋摘要（description）只是截斷的片段，不拿來回填
    assert job["薪資待遇"] is None
    assert job["工作內容"] is None
    assert job["更新日期"] == "2026-05-21"
    assert job["職缺連結"] == "https://www.104.com.tw/job/8s12x?jobsource=search"
    assert job["公司連結"] == "https://www.104.com.tw/company/abc"


def test_parse_job_missing_fields():
    job = m.parse_job({}, None)

    assert job["薪資下限"] is None and job["薪資上限"] is None
    assert job["應徵人數"] == 0
    assert job["更新日期"] == ""
    assert job["地區"] == ""
    assert job["電腦專長"] == "" and job["科系要求"] == "" and job["特色標籤"] == ""
    assert job["職缺連結"] == "" and job["公司連結"] == ""


def test_parse_job_address_and_major_variants(make_raw_job):
    job = m.parse_job(make_raw_job(jobAddress="忠孝東路一段", major="不拘"), None)

    assert job["地區"] == "台北市大安區 忠孝東路一段"
    assert job["科系要求"] == "不拘"


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------

def run_scrape(keywords, pages=3, area_code=None, job_type=0, stop=None):
    """
    執行 scrape 並記下每次回報的進度

    :return: tuple (ScrapeResult, list), 結果與依序回報的進度
    """
    progress = []
    result = m.scrape(keywords, pages, area_code, job_type,
                      stop=stop or threading.Event(), on_progress=progress.append)
    return result, progress


def codes(result):
    return [job["職缺代碼"] for job in result.jobs]


def test_scrape_dedups_across_keywords(fake_104):
    fake_104.add("A", 1, ["1", "2"], 2)
    fake_104.add("A", 2, ["3"], 2)
    fake_104.add("B", 1, ["2", "4"], 1)

    result, _ = run_scrape(["A", "B"], 3, "6001001000", 1)

    # A 在最後一頁停止，B 只有一頁；地區代碼與職缺性質原樣傳入
    assert fake_104.searches == [("A", 1, "6001001000", 1), ("A", 2, "6001001000", 1), ("B", 1, "6001001000", 1)]
    assert codes(result) == ["1", "2", "3", "4"]
    assert result.found == 4
    assert fake_104.details == ["1", "2", "3", "4"]
    assert result.jobs[0]["工作內容"] == fake_104.description("1")
    assert result.stopped is False


def test_scrape_all_areas_omits_area(fake_104):
    fake_104.add("A", 1, ["1"], 1)

    run_scrape(["A"], 1, None)

    assert fake_104.searches == [("A", 1, None, 0)]


def test_scrape_stops_on_empty_page(fake_104):
    fake_104.add("A", 1, ["1"], 5)

    result, _ = run_scrape(["A"], 3)

    assert [s[1] for s in fake_104.searches] == [1, 2]
    assert codes(result) == ["1"]


def test_scrape_respects_page_limit(fake_104):
    for page in range(1, 6):
        fake_104.add("A", page, [str(page)], 5)

    result, _ = run_scrape(["A"], 2)

    assert [s[1] for s in fake_104.searches] == [1, 2]
    assert codes(result) == ["1", "2"]


def test_scrape_search_failure_counts_as_empty_page(fake_104, monkeypatch):
    fake_104.add("B", 1, ["2"], 1)
    real_get = fake_104.get

    def flaky_get(url, params=None, **kwargs):
        if params and params.get("keyword") == "A":
            raise requests.exceptions.Timeout("逾時")
        return real_get(url, params=params, **kwargs)

    monkeypatch.setattr(m.requests, "get", flaky_get)

    result, _ = run_scrape(["A", "B"], 2)

    # A 的第 1 頁失敗就換下一個關鍵字，抓取不中斷
    assert codes(result) == ["2"]


def test_scrape_detail_failure_keeps_job_without_detail(fake_104):
    fake_104.add("A", 1, ["1", "2"], 1)
    fake_104.failed_details.add("1")

    result, _ = run_scrape(["A"], 1)

    first, second = result.jobs
    assert first["工作內容"] is None and first["薪資待遇"] is None
    assert second["工作內容"] == fake_104.description("2")


def test_scrape_without_job_id_skips_detail(fake_104, no_sleep):
    fake_104.add("A", 1, [fake_104.raw_job("1", link={})], 1)

    result, _ = run_scrape(["A"], 1)

    assert fake_104.details == []
    # 只有搜尋，沒有取職缺頁面前的延遲
    assert no_sleep == []
    assert result.jobs[0]["工作內容"] is None


def test_scrape_reports_progress(fake_104):
    fake_104.add("A", 1, ["1", "2"], 2)
    fake_104.add("A", 2, ["3"], 2)
    fake_104.add("B", 1, ["2"], 1)

    _, progress = run_scrape(["A", "B"], 2)

    assert progress == [
        m.SearchProgress("A", 1, 2, 0),
        m.SearchProgress("A", 2, 2, 2),
        m.SearchProgress("B", 1, 2, 3),
        m.DetailProgress(1, 3),
        m.DetailProgress(2, 3),
        m.DetailProgress(3, 3),
    ]


def test_scrape_rate_limit(fake_104, no_sleep):
    fake_104.add("A", 1, ["1"], 2)
    fake_104.add("A", 2, ["2"], 2)
    fake_104.add("B", 1, ["3"], 2)
    fake_104.add("B", 2, ["4"], 2)

    run_scrape(["A", "B"], 2)

    # 分頁間 1.0–2.0 秒、關鍵字間 2.0–3.5 秒，其餘為取職缺頁面前的 0.1–0.3 秒
    page_a, keyword, page_b, *details = no_sleep
    assert 1.0 <= page_a <= 2.0 and 1.0 <= page_b <= 2.0
    assert 2.0 <= keyword <= 3.5
    assert len(details) == 4
    assert all(0.1 <= d <= 0.3 for d in details)


def test_scrape_stop_during_search_returns_no_jobs(fake_104):
    fake_104.add("A", 1, ["1"], 3)
    fake_104.add("A", 2, ["2"], 3)
    stop = threading.Event()

    def stop_after_first_page(progress):
        if progress == m.SearchProgress("A", 1, 3, 0):
            stop.set()

    result = m.scrape(["A", "B"], 3, None, 0, stop=stop, on_progress=stop_after_first_page)

    # 已經送出的第 1 頁照常完成，之後不再發出請求；還沒取內容的職缺不列入結果
    assert fake_104.searches == [("A", 1, None, 0)]
    assert fake_104.details == []
    assert result.jobs == []
    assert result.found == 1
    assert result.stopped is True


def test_scrape_stop_during_detail_keeps_finished_jobs(fake_104):
    fake_104.add("A", 1, [str(i) for i in range(1, 9)], 1)
    stop = threading.Event()

    def stop_at_fifth(progress):
        if progress == m.DetailProgress(5, 8):
            stop.set()

    result = m.scrape(["A"], 1, None, 0, stop=stop, on_progress=stop_at_fifth)

    # 停止時第 5 筆還沒送出請求，所以只留下取完的 4 筆
    assert fake_104.details == ["1", "2", "3", "4"]
    assert codes(result) == ["1", "2", "3", "4"]
    assert result.found == 8
    assert result.stopped is True


def test_scrape_stop_after_request_sent_finishes_it(fake_104):
    fake_104.add("A", 1, [str(i) for i in range(1, 9)], 1)
    gate = fake_104.hold("detail", 5)
    stop = threading.Event()
    results = []
    thread = threading.Thread(target=lambda: results.append(run_scrape(["A"], 1, stop=stop)[0]))
    thread.start()

    assert gate.reached.wait(5)
    stop.set()
    gate.release()
    thread.join(5)

    # 第 5 筆的請求已經送出，照常完成並列入結果，之後不再發出請求
    (result,) = results
    assert fake_104.details == ["1", "2", "3", "4", "5"]
    assert codes(result) == ["1", "2", "3", "4", "5"]
    assert result.stopped is True


def test_scrape_stop_interrupts_delay():
    stop = threading.Event()
    stop.set()
    started = datetime.now()

    m._sleep(30, stop)

    assert (datetime.now() - started).total_seconds() < 1


def test_scrape_finished_at_is_end_time(fake_104):
    fake_104.add("A", 1, ["1"], 1)
    before = datetime.now().replace(microsecond=0)

    result, _ = run_scrape(["A"], 1)

    assert result.finished_at.microsecond == 0
    assert before <= result.finished_at <= datetime.now()
