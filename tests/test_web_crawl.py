"""網頁後端：抓取頁的 API。104 以 fake_104 取代，請求之間不等待。"""

import threading
import time
from contextlib import closing
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import fetch_104_jobs
from job_db import list_jobs, list_runs, open_db, save_run
from web import create_app

T = datetime(2026, 9, 20, 9, 30, 0)
EARLIER = datetime(2026, 9, 1, 10, 0, 0)


class FixedDatetime(datetime):
    """抓完或停止的時間固定為 T"""

    @classmethod
    def now(cls, tz=None):
        return cls(T.year, T.month, T.day, T.hour, T.minute, T.second)


@pytest.fixture
def client(isolate_db, fake_104, monkeypatch):
    """
    以 isolate_db 為資料庫、不提供前端的 TestClient；抓完的時間固定為 T

    :return: TestClient
    """
    monkeypatch.setattr(fetch_104_jobs, "datetime", FixedDatetime)
    with TestClient(create_app(isolate_db)) as test_client:
        yield test_client


def body(**overrides):
    """開始抓取的請求內容，預設以 Python 搜尋全台灣 1 頁"""
    return {"keyword": "Python", "area": None, "pages": 1, "job_type": 0, **overrides}


def wait_until(client, predicate, timeout=5):
    """
    重複取得抓取的狀態，直到符合 predicate

    :return: dict, 符合條件的狀態
    """
    deadline = time.monotonic() + timeout
    while True:
        state = client.get("/api/crawl").json()
        if predicate(state):
            return state
        if time.monotonic() > deadline:
            pytest.fail(f"抓取的狀態沒有變成預期的樣子：{state}")
        time.sleep(0.01)


def crawl(client, **overrides):
    """
    開始抓取並等它結束

    :return: dict, 抓取結束後的狀態
    """
    response = client.post("/api/crawl", json=body(**overrides))
    assert response.status_code == 202, response.text
    return wait_until(client, lambda s: s["running"] is None)


def preview_codes(state):
    return [job["職缺代碼"] for job in state["preview"]["jobs"]]


def seed(db_path, make_job, *codes):
    with closing(open_db(db_path)) as conn:
        save_run(conn, [make_job(職缺代碼=code) for code in codes], EARLIER, "爬蟲")


def db_codes(db_path):
    with closing(open_db(db_path)) as conn:
        return sorted(job["職缺代碼"] for job in list_jobs(conn))


def test_get_areas_lists_22_cities(client):
    response = client.get("/api/crawl/areas")

    assert response.status_code == 200
    areas = response.json()["areas"]
    assert areas == list(fetch_104_jobs.AREAS)
    assert len(areas) == 22


@pytest.mark.parametrize("overrides, detail", [
    ({"keyword": " ,， "}, "至少要有一個關鍵字"),
    ({"area": "火星"}, "不認得的縣市：火星"),
    ({"pages": 0}, None),
    ({"job_type": 3}, None),
])
def test_start_crawl_rejects_invalid(client, fake_104, overrides, detail):
    response = client.post("/api/crawl", json=body(**overrides))

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail
    assert fake_104.searches == []


def test_start_crawl_passes_conditions(client, fake_104):
    fake_104.add("Python", 1, ["1"], 2)

    crawl(client, keyword="Python， 資料工程師,Python", area="新竹縣", pages=2, job_type=1)

    assert fake_104.searches == [
        ("Python", 1, "6001007000", 1),
        ("Python", 2, "6001007000", 1),
        ("資料工程師", 1, "6001007000", 1),
    ]


def test_start_crawl_all_areas_omits_area(client, fake_104):
    crawl(client)

    assert fake_104.searches == [("Python", 1, None, 0)]


def test_start_crawl_busy_returns_409(client, fake_104):
    release = threading.Event()
    client.app.state.runner.start("評分", lambda job: release.wait(10))
    try:
        response = client.post("/api/crawl", json=body())
    finally:
        release.set()

    assert response.status_code == 409
    assert response.json()["detail"] == "同一時間只能跑一個作業，目前正在評分"
    assert fake_104.searches == []


def test_get_state_reports_progress_and_stopping(client, fake_104):
    fake_104.add("Python", 1, ["1", "2"], 1)
    gate = fake_104.hold("detail", 2)
    client.post("/api/crawl", json=body())
    assert gate.reached.wait(5)

    running = client.get("/api/crawl").json()["running"]
    assert running == {"progress": {"stage": "detail", "index": 2, "total": 2}, "stopping": False}

    assert client.post("/api/crawl/stop").status_code == 204
    assert client.get("/api/crawl").json()["running"]["stopping"] is True
    gate.release()
    state = wait_until(client, lambda s: s["running"] is None)
    assert preview_codes(state) == ["1", "2"]
    assert state["preview"]["stopped"] is True


def test_crawl_preview_marks_new_jobs(client, fake_104, isolate_db, make_job):
    seed(isolate_db, make_job, "A")
    fake_104.add("Python", 1, ["A", "B", "C"], 1)

    state = crawl(client)

    assert preview_codes(state) == ["A", "B", "C"]
    assert state["preview"]["new_codes"] == ["B", "C"]
    assert state["preview"]["found"] == 3
    assert state["preview"]["stopped"] is False
    # 預覽只有職缺欄位契約的欄位，還沒寫進資料庫
    assert "最後出現時間" not in state["preview"]["jobs"][0]
    assert db_codes(isolate_db) == ["A"]


@pytest.mark.parametrize("stop_at, outcome", [
    (None, "沒有抓到職缺。"),
    ("search", "已停止，還沒有取完內容的職缺。"),
])
def test_crawl_without_preview_reports_outcome(client, fake_104, stop_at, outcome):
    if stop_at == "search":
        fake_104.add("Python", 1, ["1"], 1)
        gate = fake_104.hold("search", 1)
        client.post("/api/crawl", json=body())
        assert gate.reached.wait(5)
        client.post("/api/crawl/stop")
        gate.release()
        state = wait_until(client, lambda s: s["running"] is None)
    else:
        state = crawl(client)

    assert state["preview"] is None
    assert state["outcome"] == outcome
    assert fake_104.details == []


def test_start_crawl_with_preview_requires_discard(client, fake_104, isolate_db):
    fake_104.add("Python", 1, ["1"], 1)
    fake_104.add("Go", 1, ["2"], 1)
    crawl(client)

    response = client.post("/api/crawl", json=body(keyword="Go"))
    assert response.status_code == 409
    assert preview_codes(client.get("/api/crawl").json()) == ["1"]

    state = crawl(client, keyword="Go", discard_preview=True)
    assert preview_codes(state) == ["2"]
    assert db_codes(isolate_db) == []


def test_start_crawl_rejected_keeps_preview(client, fake_104):
    fake_104.add("Python", 1, ["1"], 1)
    crawl(client)

    response = client.post("/api/crawl", json=body(keyword=",", discard_preview=True))

    assert response.status_code == 422
    assert preview_codes(client.get("/api/crawl").json()) == ["1"]


def test_save_preview_writes_jobs_and_run(client, fake_104, isolate_db, make_job):
    seed(isolate_db, make_job, "A")
    fake_104.add("Python", 1, ["A", "B"], 1)
    crawl(client, area="台北市", pages=3, job_type=1)

    response = client.post("/api/crawl/save")

    assert response.status_code == 200
    assert response.json() == {"codes": ["A", "B"]}
    with closing(open_db(isolate_db)) as conn:
        jobs = {job["職缺代碼"]: job for job in list_jobs(conn)}
        latest = list_runs(conn)[0]
    t = T.isoformat()
    # 執行時間是抓完的時間，不是按下存入的時間
    assert jobs["A"]["最後出現時間"] == jobs["B"]["最後出現時間"] == t
    assert jobs["B"]["首次出現時間"] == t
    assert jobs["B"]["工作內容"] == fake_104.description("B")
    assert {k: latest[k] for k in ("執行時間", "來源", "關鍵字", "地區", "職缺性質", "頁數", "職缺數")} == {
        "執行時間": t, "來源": "爬蟲", "關鍵字": "Python", "地區": "台北市", "職缺性質": 1, "頁數": 3, "職缺數": 2,
    }
    assert client.get("/api/crawl").json()["preview"] is None


def test_save_preview_all_areas_and_joined_keywords(client, fake_104, isolate_db):
    fake_104.add("Python", 1, ["1"], 1)
    crawl(client, keyword="Python, AI")

    client.post("/api/crawl/save")

    with closing(open_db(isolate_db)) as conn:
        latest = list_runs(conn)[0]
    assert latest["關鍵字"] == "Python, AI"
    assert latest["地區"] == "全台灣"


def test_save_preview_after_stop(client, fake_104, isolate_db):
    fake_104.add("Python", 1, [str(i) for i in range(1, 9)], 1)
    gate = fake_104.hold("detail", 5)
    client.post("/api/crawl", json=body(pages=3))
    assert gate.reached.wait(5)
    client.post("/api/crawl/stop")
    gate.release()
    state = wait_until(client, lambda s: s["running"] is None)

    response = client.post("/api/crawl/save")

    assert response.json()["codes"] == preview_codes(state) == ["1", "2", "3", "4", "5"]
    assert db_codes(isolate_db) == ["1", "2", "3", "4", "5"]
    with closing(open_db(isolate_db)) as conn:
        latest = list_runs(conn)[0]
    # 中途停止時仍記要求的頁數
    assert (latest["執行時間"], latest["頁數"]) == (T.isoformat(), 3)


def test_save_failure_keeps_preview(client, fake_104, isolate_db, make_job):
    seed(isolate_db, make_job, "A")
    fake_104.add("Python", 1, ["A", "B"], 1)
    crawl(client)
    with closing(open_db(isolate_db)) as conn, conn:
        conn.execute("CREATE TRIGGER fail_run BEFORE INSERT ON scrape_runs BEGIN SELECT RAISE(ABORT, '模擬寫入失敗'); END")

    response = client.post("/api/crawl/save")

    assert response.status_code == 500
    assert response.json()["detail"] == "存入失敗：模擬寫入失敗"
    assert db_codes(isolate_db) == ["A"]
    assert preview_codes(client.get("/api/crawl").json()) == ["A", "B"]

    with closing(open_db(isolate_db)) as conn, conn:
        conn.execute("DROP TRIGGER fail_run")
    assert client.post("/api/crawl/save").status_code == 200
    assert db_codes(isolate_db) == ["A", "B"]


def test_save_without_preview_returns_409(client):
    response = client.post("/api/crawl/save")

    assert response.status_code == 409


def test_discard_preview_leaves_db_unchanged(client, fake_104, isolate_db, make_job):
    seed(isolate_db, make_job, "A")
    fake_104.add("Python", 1, ["A", "B"], 1)
    crawl(client)

    assert client.delete("/api/crawl/preview").status_code == 204

    state = client.get("/api/crawl").json()
    assert state["preview"] is None and state["outcome"] is None
    assert db_codes(isolate_db) == ["A"]
    with closing(open_db(isolate_db)) as conn:
        assert len(list_runs(conn)) == 1
