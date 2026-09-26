"""網頁後端：設定頁的 API。資料庫是 isolate_db，啟動時寫入三份設定的第 1 版。"""

import subprocess
from contextlib import closing
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from job_db import list_scores, open_db
from job_scoring.settings import DEFAULTS
from web import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KINDS = ["preferences", "experience", "template"]


@pytest.fixture
def client(isolate_db):
    """
    以還沒有任何設定的 isolate_db 啟動、不提供前端的 TestClient

    :return: TestClient
    """
    with TestClient(create_app(isolate_db)) as test_client:
        yield test_client


def _valid_preferences(preferences_data):
    return yaml.safe_dump(preferences_data, allow_unicode=True)


def _save(client, kind, content, name="名稱", description=""):
    return client.post(f"/api/settings/{kind}/versions", json={"name": name, "description": description, "content": content})


def test_new_db_has_first_versions(client):
    # AC-settings-default：三份設定都只有第 1 版，是預設內容，不是 profile/ 下檔案的內容
    state = client.get("/api/settings").json()

    for kind in KINDS:
        assert state[kind]["current"] == 1
        assert state[kind]["default_content"] == DEFAULTS[kind]
        [first] = state[kind]["versions"]
        assert first["version"] == 1
        assert first["content"] == DEFAULTS[kind]
        assert state[kind]["is_default"] is True
    assert state["preferences"]["versions"][0]["name"] == "預設範例"
    assert state["template"]["versions"][0]["name"] == "預設模板"


def test_restart_keeps_versions(isolate_db, preferences_data):
    with TestClient(create_app(isolate_db)) as first:
        _save(first, "preferences", _valid_preferences(preferences_data))
    with TestClient(create_app(isolate_db)) as second:
        state = second.get("/api/settings").json()

    assert state["preferences"]["current"] == 2
    assert len(state["preferences"]["versions"]) == 2


def test_save_version_applies_and_lists_newest_first(client, preferences_data):
    # AC-settings-version (b)
    response = _save(client, "preferences", _valid_preferences(preferences_data), name="  後端與 LLM ", description="")

    assert response.status_code == 201
    assert response.json() == {"version": 2}
    prefs = client.get("/api/settings").json()["preferences"]
    assert prefs["current"] == 2
    assert prefs["is_default"] is False
    assert [v["version"] for v in prefs["versions"]] == [2, 1]
    assert prefs["versions"][0]["name"] == "後端與 LLM"
    assert prefs["versions"][0]["description"] == ""
    assert prefs["versions"][0]["content"] == _valid_preferences(preferences_data)


@pytest.mark.parametrize("name", ["", "   "])
def test_save_version_requires_name(client, preferences_data, name):
    # AC-settings-version (a)
    response = _save(client, "preferences", _valid_preferences(preferences_data), name=name)

    assert response.status_code == 422
    assert response.json()["detail"] == "版本的名稱必填"
    assert len(client.get("/api/settings").json()["preferences"]["versions"]) == 1


def test_save_version_rejects_invalid_content(client, preferences_data):
    del preferences_data["權重"]

    response = _save(client, "preferences", _valid_preferences(preferences_data))

    assert response.status_code == 422
    assert response.json()["detail"] == "偏好有錯，不能儲存或套用：權重：缺少這個欄位"
    assert len(client.get("/api/settings").json()["preferences"]["versions"]) == 1


def test_save_version_template_warning_allowed(client):
    # AC-settings-check (c)：沒用到的變數只提醒，可以儲存
    assert _save(client, "template", DEFAULTS["template"].replace("$工作經歷", "")).status_code == 201


def test_save_version_experience_not_checked(client):
    # AC-settings-check (e)
    assert _save(client, "experience", "只有一行文字").status_code == 201


def test_save_version_writes_no_project_files(client, preferences_data):
    # AC-settings-version (b)：設定只存在職缺資料庫，專案目錄中沒有新增或修改任何檔案
    def status():
        return subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--ignored"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
        ).stdout

    before = status()
    _save(client, "preferences", _valid_preferences(preferences_data))
    _save(client, "experience", "經歷")

    assert status() == before


def test_apply_version(client, preferences_data):
    # AC-settings-apply (c)：套用舊版本不新增版本，也不影響評分紀錄
    for n in (2, 3):
        preferences_data["薪資"]["期望月薪"] = 70000 + n
        _save(client, "preferences", _valid_preferences(preferences_data))

    response = client.put("/api/settings/preferences/current", json={"version": 1})

    assert response.status_code == 204
    prefs = client.get("/api/settings").json()["preferences"]
    assert prefs["current"] == 1
    assert prefs["is_default"] is True
    assert len(prefs["versions"]) == 3
    with closing(open_db(client.app.state.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0] == 0
        assert list_scores(conn, "任何職缺") == []


def test_apply_missing_version_404(client):
    response = client.put("/api/settings/template/current", json={"version": 9})

    assert response.status_code == 404
    assert response.json()["detail"] == "沒有第 9 版"


def test_apply_invalid_version_422(client, preferences_data):
    # 規則改變等原因讓舊版本不再合法時，不能套用
    with closing(open_db(client.app.state.db_path)) as conn, conn:
        conn.execute(
            'INSERT INTO settings_versions VALUES (\'preferences\', 2, \'壞掉的\', \'\', \'2026-09-20T09:30:00\', \'- 清單\')'
        )

    response = client.put("/api/settings/preferences/current", json={"version": 2})

    assert response.status_code == 422
    assert client.get("/api/settings").json()["preferences"]["current"] == 1


def test_update_meta_keeps_content(client, preferences_data):
    # AC-settings-version (c)
    _save(client, "preferences", _valid_preferences(preferences_data), name="後端與 LLM")

    response = client.patch("/api/settings/preferences/versions/2", json={"name": "後端", "description": " 第一次填 "})

    assert response.status_code == 204
    second = client.get("/api/settings").json()["preferences"]["versions"][0]
    assert (second["name"], second["description"]) == ("後端", "第一次填")
    assert second["content"] == _valid_preferences(preferences_data)


def test_update_meta_errors(client):
    assert client.patch("/api/settings/preferences/versions/9", json={"name": "名稱"}).status_code == 404
    response = client.patch("/api/settings/preferences/versions/1", json={"name": " "})
    assert response.status_code == 422
    assert client.get("/api/settings").json()["preferences"]["versions"][0]["name"] == "預設範例"


def test_unknown_kind_422(client):
    assert _save(client, "profile", "內容").status_code == 422
    assert client.post("/api/settings/check", json={"kind": "profile", "content": ""}).status_code == 422


def test_no_delete_endpoints(client):
    # AC-settings-version (c)、AC-history-no-delete：沒有刪除版本或評分紀錄的方式
    paths = client.get("/openapi.json").json()["paths"]
    settings_methods = {method for path, ops in paths.items() if path.startswith("/api/settings") for method in ops}

    assert settings_methods == {"get", "post", "put", "patch"}
    # 整個 API 只有抓取頁的「捨棄預覽」是刪除
    deletes = [path for path, ops in paths.items() if "delete" in ops]
    assert deletes == ["/api/crawl/preview"]


@pytest.mark.parametrize("kind, content, errors, warnings", [
    ("template", DEFAULTS["template"].replace("<!-- USER -->", ""), 1, 0),
    ("template", DEFAULTS["template"].replace("$工作經歷", ""), 0, 1),
    ("experience", "$年資", 0, 0),
    ("preferences", "- 清單", 1, 0),
])
def test_check(client, kind, content, errors, warnings):
    body = client.post("/api/settings/check", json={"kind": kind, "content": content}).json()

    assert (len(body["errors"]), len(body["warnings"])) == (errors, warnings)
