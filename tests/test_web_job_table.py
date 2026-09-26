"""網頁後端：職缺表的 API、提供前端的路徑，以及啟動時開啟資料庫。"""

import sqlite3
from contextlib import closing
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from job_db import JOB_COLUMNS, open_db, save_run
from web import create_app

T1 = datetime(2026, 9, 1, 10, 0, 0)
T2 = datetime(2026, 9, 2, 10, 0, 0)


@pytest.fixture
def client(isolate_db):
    """
    以 isolate_db 為資料庫、不提供前端的 TestClient（with 區塊會執行啟動流程）

    :return: TestClient
    """
    with TestClient(create_app(isolate_db)) as test_client:
        yield test_client


def test_get_jobs_lists_all_jobs_by_last_seen(client, isolate_db, make_job):
    with closing(open_db(isolate_db)) as conn:
        save_run(conn, [make_job(職缺代碼="a"), make_job(職缺代碼="b")], T1, "爬蟲")
        save_run(conn, [make_job(職缺代碼="c", 薪資下限=None)], T2, "爬蟲")

    response = client.get("/api/jobs")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    # c 最後出現在 t2 排最前；a、b 同在 t1，再比職缺代碼
    assert [job["職缺代碼"] for job in jobs] == ["c", "a", "b"]
    assert list(jobs[0]) == [name for name, _ in JOB_COLUMNS] + ["首次出現時間", "最後出現時間"]
    assert jobs[0]["薪資下限"] is None
    assert jobs[0]["最後出現時間"] == T2.isoformat(timespec="seconds")


def test_get_jobs_empty_db_is_empty_list(client):
    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_create_app_opens_db_on_startup(tmp_path):
    # 還沒改版的舊版資料庫（user_version 0、已有資料表），open_db 會拒絕開啟
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE job_scores ("職缺代碼" TEXT)')

    with pytest.raises(sqlite3.DatabaseError, match="舊版"):
        with TestClient(create_app(path)):
            pass


@pytest.fixture
def frontend_dir(tmp_path):
    """
    假的前端 build：index.html 與 assets/app.js

    :return: Path, 前端目錄
    """
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text("<html>首頁</html>", encoding="utf-8")
    (directory / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return directory


@pytest.mark.parametrize("path", ["/", "/crawl", "/settings", "/not-a-page"])
def test_create_app_serves_index_for_frontend_paths(isolate_db, frontend_dir, path):
    with TestClient(create_app(isolate_db, frontend_dir)) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert response.text == "<html>首頁</html>"
    # build 後 assets 的檔名會換，index.html 每次都要向伺服器確認
    assert response.headers["cache-control"] == "no-cache"


def test_create_app_serves_assets(isolate_db, frontend_dir):
    with TestClient(create_app(isolate_db, frontend_dir)) as client:
        response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log(1)"


@pytest.mark.parametrize("path", ["/api", "/api/not-found"])
def test_create_app_unknown_api_is_404(isolate_db, frontend_dir, path):
    with TestClient(create_app(isolate_db, frontend_dir)) as client:
        response = client.get(path)

    assert response.status_code == 404


def test_create_app_without_frontend_serves_api_only(client):
    assert client.get("/").status_code == 404
    assert client.get("/api/jobs").status_code == 200
