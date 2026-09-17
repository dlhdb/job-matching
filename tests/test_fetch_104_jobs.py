"""104 職缺爬蟲的離線測試。HTTP 請求與等待一律以 monkeypatch 取代。"""

import csv
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
import requests

import fetch_104_jobs as m

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "fetch_104_jobs.py"
BOM = b"\xef\xbb\xbf"
SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/"
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


@pytest.fixture
def detail_ok(monkeypatch):
    """詳情 API 一律成功，回傳紀錄呼叫過的 job_id 清單"""
    calls = []

    def _detail(job_id):
        calls.append(job_id)
        return dict(DETAIL)

    monkeypatch.setattr(m, "fetch_job_detail", _detail)
    return calls


def output_files(directory, suffix):
    return sorted(directory.glob(f"*{suffix}"))


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


@pytest.mark.parametrize("text, width, expected", [
    (None, 10, "null"),
    ("", 10, ""),
    ("abc", 10, "abc"),
    ("abcdef", 3, "abc.."),
    ("中文", 4, "中文"),       # CJK 字元寬度計 2，剛好放得下
    ("中文字", 4, "中文.."),
    ("中a文", 4, "中a.."),
])
def test_truncate_display(text, width, expected):
    assert m.truncate_display(text, width) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Python, React，AI", ["Python", "React", "AI"]),
    ("Python,React, Python", ["Python", "React"]),
    ("  Python  ", ["Python"]),
    ("", [""]),
    (",，, ", []),
])
def test_parse_keywords(raw, expected):
    assert m.parse_keywords(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("台北市", ("6001001000", "台北市")),
    ("台北", ("6001001000", "台北市")),
    ("新竹", ("6001006000", "新竹市")),  # 同名的市與縣，取清單中先出現的市
    ("新竹縣", ("6001007000", "新竹縣")),
    ("火星", (None, "全台灣")),
    ("", (None, "全台灣")),
    (None, (None, "全台灣")),
])
def test_resolve_area(raw, expected):
    assert m.resolve_area(raw) == expected


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
# 資料解析與持久化
# ---------------------------------------------------------------------------

def test_parse_jobs_with_detail(make_raw_job, detail_ok, no_sleep):
    (job,) = m.parse_jobs([make_raw_job()])

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
    assert list(job) == m.CSV_FIELDNAMES
    assert detail_ok == ["8s12x"]
    (delay,) = no_sleep
    assert 0.1 <= delay <= 0.3


def test_parse_jobs_detail_failure_does_not_backfill(make_raw_job, monkeypatch, no_sleep):
    monkeypatch.setattr(m, "fetch_job_detail", lambda job_id: None)

    (job,) = m.parse_jobs([make_raw_job()])

    assert job["薪資待遇"] is None
    assert job["工作內容"] is None
    assert job["更新日期"] == "2026-05-21"
    assert job["職缺連結"] == "https://www.104.com.tw/job/8s12x?jobsource=search"
    assert job["公司連結"] == "https://www.104.com.tw/company/abc"
    assert list(job) == m.CSV_FIELDNAMES


def test_parse_jobs_without_job_id_skips_detail(make_raw_job, detail_ok, no_sleep):
    (job,) = m.parse_jobs([make_raw_job(link={})])

    assert detail_ok == []
    assert no_sleep == []
    assert job["工作內容"] is None and job["薪資待遇"] is None
    assert job["職缺連結"] == "" and job["公司連結"] == ""


def test_parse_jobs_missing_fields(detail_ok, no_sleep):
    (job,) = m.parse_jobs([{}])

    assert list(job) == m.CSV_FIELDNAMES
    assert job["薪資下限"] is None and job["薪資上限"] is None
    assert job["應徵人數"] == 0
    assert job["更新日期"] == ""
    assert job["地區"] == ""
    assert job["電腦專長"] == "" and job["科系要求"] == "" and job["特色標籤"] == ""


def test_parse_jobs_address_and_major_variants(make_raw_job, detail_ok, no_sleep):
    (job,) = m.parse_jobs([make_raw_job(jobAddress="忠孝東路一段", major="不拘")])

    assert job["地區"] == "台北市大安區 忠孝東路一段"
    assert job["科系要求"] == "不拘"


def test_parse_jobs_empty(capsys):
    assert m.parse_jobs([]) == []
    assert capsys.readouterr().out == ""


@pytest.fixture
def parsed_jobs(make_raw_job, detail_ok, no_sleep):
    return m.parse_jobs([make_raw_job(), make_raw_job(jobNo="2", custName="乙公司")])


def test_save_to_csv(parsed_jobs, tmp_path):
    path = tmp_path / "jobs.csv"
    m.save_to_csv(parsed_jobs, path)

    assert path.read_bytes().startswith(BOM)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == m.CSV_FIELDNAMES
    assert [r["職缺代碼"] for r in rows] == ["1", "2"]
    assert rows[1]["公司名稱"] == "乙公司"


def test_save_to_json(parsed_jobs, tmp_path):
    path = tmp_path / "jobs.json"
    m.save_to_json(parsed_jobs, path)

    text = path.read_text(encoding="utf-8")
    assert "甲公司" in text  # 中文不跳脫
    assert json.loads(text) == parsed_jobs


@pytest.mark.parametrize("save", [m.save_to_csv, m.save_to_json])
def test_save_empty_data_writes_nothing(save, tmp_path, capsys):
    path = tmp_path / "jobs.out"
    save([], path)

    assert not path.exists()
    assert "[-]" in capsys.readouterr().out


@pytest.mark.parametrize("save", [m.save_to_csv, m.save_to_json])
def test_save_io_error_is_reported(save, parsed_jobs, tmp_path, capsys):
    save(parsed_jobs, tmp_path / "不存在的目錄" / "jobs.out")
    assert "[-]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 終端機顯示
# ---------------------------------------------------------------------------

def test_display_summary_table_respects_limit(make_raw_job, detail_ok, no_sleep, capsys):
    jobs = m.parse_jobs([make_raw_job(jobNo=str(i)) for i in range(12)])
    capsys.readouterr()

    m.display_summary_table(jobs, limit=10)

    out = capsys.readouterr().out
    assert "顯示前 10 筆 / 合併去重共 12 筆" in out
    assert "\n10  | " in out
    assert "\n11  | " not in out


def test_display_summary_table_shows_null_salary(make_raw_job, monkeypatch, no_sleep, capsys):
    monkeypatch.setattr(m, "fetch_job_detail", lambda job_id: None)
    jobs = m.parse_jobs([make_raw_job()])

    m.display_summary_table(jobs)

    assert "null" in capsys.readouterr().out


def test_display_summary_table_empty(capsys):
    m.display_summary_table([])
    assert "[-]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 核心撈取邏輯
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_search(monkeypatch, tmp_path, no_sleep):
    """
    以假函式取代 requests.get，依網址回傳搜尋與詳情 API 的假回應，並把輸出目錄改到 tmp_path

    :return: callable, fake_search(pages) -> list[tuple]（搜尋請求的呼叫紀錄）；
             pages 為 {(keyword, page): (jobNo 清單, lastPage)}，未列出的頁面回傳空結果；
             詳情 API 一律回傳 DETAIL
    """
    monkeypatch.setattr(m, "OUTPUT_DIR", tmp_path)

    def _install(pages):
        calls = []

        def _get(url, params=None, **kwargs):
            if url.startswith(DETAIL_URL):
                return FakeResponse(200, {"data": {"jobDetail": DETAIL}})
            assert url == SEARCH_URL
            # 關鍵字為空字串時，fetch_jobs 不帶 keyword 參數
            keyword, page = params.get("keyword", ""), params["page"]
            calls.append((keyword, page, params.get("area"), params["ro"]))
            if (keyword, page) not in pages:
                return FakeResponse(200, {"data": [], "metadata": {}})
            job_nos, last_page = pages[(keyword, page)]
            jobs = [{"jobNo": no, "link": {"job": f"//www.104.com.tw/job/{no}"}} for no in job_nos]
            return FakeResponse(200, {"data": jobs, "metadata": {"pagination": {"lastPage": last_page}}})

        monkeypatch.setattr(m.requests, "get", _get)
        return calls
    return _install


def test_execute_scraping_dedups_across_keywords(fake_search, tmp_path, no_sleep):
    calls = fake_search({
        ("A", 1): (["1", "2"], 2),
        ("A", 2): (["3"], 2),
        ("B", 1): (["2", "4"], 1),
    })

    m.execute_scraping(["A", "B"], 3, "6001001000", "台北市", 1)

    # A 在最後一頁停止，B 只有一頁；area_code 與 ro 原樣傳入
    assert calls == [("A", 1, "6001001000", 1), ("A", 2, "6001001000", 1), ("B", 1, "6001001000", 1)]
    (json_file,) = output_files(tmp_path, ".json")
    (csv_file,) = output_files(tmp_path, ".csv")
    assert json_file.stem == csv_file.stem
    assert json_file.name.startswith("jobs_104_A_B_")
    ids = [job["職缺代碼"] for job in json.loads(json_file.read_text(encoding="utf-8"))]
    assert ids == ["1", "2", "3", "4"]

    # 分頁間 1.0–2.0 秒、關鍵字間 2.0–3.5 秒，其餘為詳情請求前的 0.1–0.3 秒
    page_delay, keyword_delay, *detail_delays = no_sleep
    assert 1.0 <= page_delay <= 2.0
    assert 2.0 <= keyword_delay <= 3.5
    assert len(detail_delays) == 4
    assert all(0.1 <= d <= 0.3 for d in detail_delays)


def test_execute_scraping_stops_on_empty_page(fake_search, tmp_path):
    calls = fake_search({("A", 1): (["1"], 5)})

    m.execute_scraping(["A"], 3, None, "全台灣", 0)

    assert [c[1] for c in calls] == [1, 2]
    assert len(output_files(tmp_path, ".json")) == 1


def test_execute_scraping_respects_page_limit(fake_search):
    calls = fake_search({("A", p): ([str(p)], 5) for p in range(1, 6)})

    m.execute_scraping(["A"], 2, None, "全台灣", 0)

    assert [c[1] for c in calls] == [1, 2]


def test_execute_scraping_accepts_single_string(fake_search):
    calls = fake_search({("Python", 1): (["1"], 1)})

    m.execute_scraping("Python", 1, None, "全台灣", 0)

    assert calls[0][0] == "Python"


def test_execute_scraping_no_jobs_writes_nothing(fake_search, tmp_path, capsys):
    fake_search({})

    m.execute_scraping(["A"], 1, None, "全台灣", 0)

    assert list(tmp_path.iterdir()) == []
    assert "[-] 未撈取到任何職缺" in capsys.readouterr().out


@pytest.mark.parametrize("keywords, prefix", [
    (["C++", "Python"], "jobs_104_C_Python_"),
    (["a" * 40], "jobs_104_" + "a" * 30 + "_etc_"),
    (["!!!"], "jobs_104_all_"),
    ([""], "jobs_104_all_"),
])
def test_execute_scraping_filename(fake_search, tmp_path, keywords, prefix):
    fake_search({(kw, 1): (["1"], 1) for kw in keywords})

    m.execute_scraping(keywords, 1, None, "全台灣", 0)

    (json_file,) = output_files(tmp_path, ".json")
    assert json_file.name.startswith(prefix)


# ---------------------------------------------------------------------------
# 程式入口與互動模式
# ---------------------------------------------------------------------------

@pytest.fixture
def record_execute(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "execute_scraping", lambda *args: calls.append(args))
    return calls


def test_main_cli_mode(monkeypatch, record_execute):
    monkeypatch.setattr(sys, "argv", ["fetch_104_jobs.py", "-k", "Python，AI", "-p", "2", "-a", "台北", "-t", "1"])

    m.main()

    assert record_execute == [(["Python", "AI"], 2, "6001001000", "台北市", 1)]


def test_main_cli_defaults(monkeypatch, record_execute):
    monkeypatch.setattr(sys, "argv", ["fetch_104_jobs.py", "-k", "Python"])

    m.main()

    assert record_execute == [(["Python"], 3, None, "全台灣", 0)]


def test_main_without_keyword_enters_interactive(monkeypatch, record_execute):
    called = []
    monkeypatch.setattr(sys, "argv", ["fetch_104_jobs.py"])
    monkeypatch.setattr(m, "run_interactive", lambda: called.append(True))

    m.main()

    assert called == [True]
    assert record_execute == []


@pytest.mark.parametrize("answers, expected, warning", [
    (["", "Python, AI", "", "", ""], (["Python", "AI"], 3, None, "全台灣", 0), None),
    (["Python", "新竹", "5", "2"], (["Python"], 5, "6001006000", "新竹市", 2), None),
    (["Python", "火星", "abc", "9"], (["Python"], 3, None, "全台灣", 0), "無法識別「火星」"),
    (["Python", "", "0", "1"], (["Python"], 3, None, "全台灣", 1), None),
])
def test_run_interactive(monkeypatch, record_execute, capsys, answers, expected, warning):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))

    m.run_interactive()

    assert record_execute == [expected]
    assert next(it, None) is None  # 所有答案都被讀取
    if warning:
        assert warning in capsys.readouterr().out


def test_ctrl_c_exits_gracefully():
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        # 等到歡迎訊息出現，代表已進入 main() 並準備讀取輸入
        assert proc.stdout is not None
        for line in proc.stdout:
            if "歡迎使用" in line:
                break
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 0
    assert "使用者取消操作" in out
