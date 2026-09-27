"""網頁後端：試跑的 API。LLM 換成 fake_llm，資料庫是 scoring_db（偏好與經歷已換成測試用的內容）。"""

import threading
import time
from contextlib import closing
from datetime import datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from job_db import current_versions, list_scores, open_db, save_auto_score, save_run
from job_scoring.llm import DEFAULT_MODEL, LLMError, MODELS
from job_scoring.settings import DEFAULTS
from web import create_app

T = datetime(2026, 9, 1, 10, 0, 0)


@pytest.fixture
def client(scoring_db, fake_llm):
    """
    以 scoring_db 啟動、不提供前端的 TestClient

    :return: TestClient
    """
    with TestClient(create_app(scoring_db)) as test_client:
        yield test_client


def _seed(db_path, jobs):
    with closing(open_db(db_path)) as conn:
        save_run(conn, jobs, T, "爬蟲")


def _write_score(db_path, job_no, total=70):
    details = {
        "職缺代碼": job_no, "淘汰": False, "淘汰原因": [], "維度": None,
        "總分": total, "未知維度": [], "評語": "目前的評語",
    }
    with closing(open_db(db_path)) as conn:
        save_auto_score(
            conn, job_no=job_no, scored_at=T, eliminated=False, total=total, comment="目前的評語",
            details=details, provider="gemini", model="舊模型",
            basis={"偏好版本": 2, "經歷版本": 2, "模板版本": 1, "職缺快照": {"職缺名稱": "舊"}},
        )


def _drafts(db_path, **contents):
    """
    三份設定的編輯區：以目前設定為底，contents 指定的種類換成那段內容

    :return: dict, DraftsIn
    """
    with closing(open_db(db_path)) as conn:
        current = current_versions(conn)
    return {
        kind: {"base": current[kind]["版本"], "content": contents.get(kind, current[kind]["內容"])}
        for kind in ("preferences", "experience", "template")
    }


def _plan(client, codes, drafts):
    response = client.post("/api/dry-run/plan", json={"codes": codes, "settings": drafts})
    assert response.status_code == 200, response.text
    return response.json()


def _start(client, codes, drafts, model=DEFAULT_MODEL):
    return client.post("/api/dry-run", json={"codes": codes, "settings": drafts, "model": model})


def _wait_state(client, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get("/api/dry-run").json()
        if predicate(state):
            return state
        time.sleep(0.02)
    pytest.fail(f"等不到預期的試跑狀態：{state}")


def _run(client, codes, drafts, **kwargs):
    """開始試跑並等到結束，回傳這次的結果"""
    response = _start(client, codes, drafts, **kwargs)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    state = _wait_state(client, lambda s: s["running"] is None and s["last"] and s["last"]["id"] == run_id)
    return state["last"]


@pytest.fixture
def three_listed(scoring_db, make_job):
    """試跑清單 3 筆：a 已評過（總分 70）、b 還沒評分、c 會被淘汰"""
    _seed(scoring_db, [
        make_job(職缺代碼="a", 職缺名稱="甲職缺"),
        make_job(職缺代碼="b", 職缺名稱="乙職缺"),
        make_job(職缺代碼="c", 職缺名稱="業務專員"),
    ])
    _write_score(scoring_db, "a")
    return ["a", "b", "c"]


@pytest.fixture
def five_listed(scoring_db, make_job):
    """正常、會被淘汰、正常、會評分失敗、正常"""
    names = ["甲職缺", "業務專員", "丙職缺", "丁職缺", "戊職缺"]
    _seed(scoring_db, [make_job(職缺代碼=f"j{i}", 職缺名稱=name) for i, name in enumerate(names, 1)])
    return [f"j{i}" for i in range(1, 6)]


# ---------------------------------------------------------------------------
# 試跑前的確認
# ---------------------------------------------------------------------------

def test_plan_uses_editor_contents(client, three_listed, preferences_data):
    # AC-dry-run 的確認視窗：偏好改了權重還沒儲存、經歷是預設範例，不擋
    preferences_data["權重"]["職涯方向契合度"] = 0.9
    drafts = _drafts(
        client.app.state.db_path,
        preferences=yaml.safe_dump(preferences_data, allow_unicode=True),
    )
    drafts["experience"] = {"base": 1, "content": DEFAULTS["experience"]}

    plan = _plan(client, three_listed, drafts)

    assert (plan["count"], plan["eliminated"], plan["errors"]) == (3, 1, [])
    assert plan["settings"] == {
        "preferences": {"base": 2, "name": "測試偏好", "modified": True},
        "experience": {"base": 1, "name": "預設範例", "modified": False},
        "template": {"base": 1, "name": "預設模板", "modified": False},
    }
    assert (plan["provider"], plan["models"]) == ("gemini", MODELS["gemini"])


def test_plan_eliminated_follows_editor(client, three_listed, preferences_data):
    # 淘汰筆數用編輯區的偏好算：拿掉職稱關鍵字後就沒有被淘汰的
    preferences_data["淘汰條件"]["職稱關鍵字"] = []
    drafts = _drafts(client.app.state.db_path, preferences=yaml.safe_dump(preferences_data, allow_unicode=True))

    assert _plan(client, three_listed, drafts)["eliminated"] == 0


def test_plan_empty_list(client):
    [error] = _plan(client, [], _drafts(client.app.state.db_path))["errors"]
    assert "試跑清單是空的" in error


@pytest.mark.parametrize("kind, content, expected", [
    ("preferences", "- 清單", "偏好："),
    ("template", DEFAULTS["template"].replace("<!-- USER -->", ""), "提示詞模板："),
])
def test_plan_invalid_editor(client, three_listed, kind, content, expected):
    # AC-settings-check：偏好或模板有錯時不能試跑
    plan = _plan(client, three_listed, _drafts(client.app.state.db_path, **{kind: content}))

    assert plan["errors"]
    assert all(e.startswith(f"編輯區有錯，先修正再試跑。{expected}") for e in plan["errors"])
    if kind == "preferences":
        assert plan["eliminated"] is None


def test_plan_unknown_code_and_version(client, three_listed):
    drafts = _drafts(client.app.state.db_path)
    drafts["experience"]["base"] = 99

    errors = _plan(client, ["a", "沒有這筆"], drafts)["errors"]

    assert any("不在職缺資料庫" in e for e in errors)
    assert any("經歷的第 99 版不存在" in e for e in errors)


def test_plan_no_api_key(client, three_listed, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    drafts = _drafts(client.app.state.db_path)

    [error] = _plan(client, three_listed, drafts)["errors"]
    assert "有 2 筆需要呼叫 AI" in error
    # 只有會被淘汰的職缺時不需要 API key
    assert _plan(client, ["c"], drafts)["errors"] == []


def test_start_rechecks_and_rejects(client, three_listed):
    response = _start(client, three_listed, _drafts(client.app.state.db_path, preferences="- 清單"))

    assert response.status_code == 422
    assert response.json()["detail"][0].startswith("編輯區有錯")
    assert client.get("/api/dry-run").json() == {"running": None, "last": None, "busy": None}


def test_start_unknown_model(client, three_listed):
    response = _start(client, three_listed, _drafts(client.app.state.db_path), model="不存在的模型")

    assert response.status_code == 422
    assert response.json()["detail"] == ["不認得的模型：不存在的模型"]


def test_one_job_at_a_time(client, three_listed, fake_llm):
    # AC-job (c)：評分中不能開始試跑；試跑中也不能送去評分
    db_path = client.app.state.db_path
    drafts = _drafts(db_path)
    fake_llm.hold("乙職缺")
    assert client.post("/api/scoring", json={"codes": ["b"], "rescore": False, "model": DEFAULT_MODEL}).status_code == 202

    assert "同一時間只能跑一個作業，目前正在評分" in _plan(client, three_listed, drafts)["errors"][-1]
    assert _start(client, three_listed, drafts).status_code == 409
    assert client.get("/api/dry-run").json()["busy"] == "評分"
    fake_llm.release("乙職缺")
    deadline = time.monotonic() + 10
    while client.get("/api/scoring").json()["running"] is not None:
        assert time.monotonic() < deadline
        time.sleep(0.02)

    fake_llm.hold("甲職缺")
    assert _start(client, three_listed, drafts).status_code == 202
    plan = client.post("/api/scoring/plan", json={"codes": ["a"], "rescore": True}).json()
    assert "目前正在試跑" in plan["errors"][-1]
    assert client.get("/api/scoring").json()["busy"] == "試跑"
    fake_llm.release("甲職缺")


def test_other_job_blocks_start(client, three_listed):
    release = threading.Event()
    client.app.state.runner.start("抓取", lambda job: release.wait(10))
    try:
        assert _start(client, three_listed, _drafts(client.app.state.db_path)).status_code == 409
    finally:
        release.set()


# ---------------------------------------------------------------------------
# 試跑作業
# ---------------------------------------------------------------------------

def test_dry_run_does_not_store(client, three_listed, fake_llm):
    # AC-dry-run：AI 呼叫 2 次、用編輯區的內容，評分紀錄與目前設定都不變
    db_path = client.app.state.db_path
    with closing(open_db(db_path)) as conn:
        before = {code: list_scores(conn, code) for code in three_listed}
    settings_before = client.get("/api/settings").json()
    drafts = _drafts(db_path, experience="試跑用經歷-ZZZ")

    run = _run(client, three_listed, drafts, model=MODELS["gemini"][-1])

    assert fake_llm.calls("甲職缺", "乙職缺", "業務專員") == ["甲職缺", "乙職缺"]
    assert all("試跑用經歷-ZZZ" in prompt for prompt in fake_llm.prompts)
    assert fake_llm.models == [MODELS["gemini"][-1]]
    with closing(open_db(db_path)) as conn:
        assert {code: list_scores(conn, code) for code in three_listed} == before
    assert client.get("/api/settings").json() == settings_before

    assert (run["total"], run["done"], run["stopped"], run["error"]) == (3, 3, False, None)
    assert run["model"] == MODELS["gemini"][-1]
    assert run["settings"]["experience"] == {
        "base": 2, "name": "測試經歷", "modified": True, "content": "試跑用經歷-ZZZ",
    }
    assert run["settings"]["preferences"]["modified"] is False
    rows = {row["code"]: row for row in run["rows"]}
    assert [row["code"] for row in run["rows"]] == three_listed
    assert all(row["status"] == "done" and row["reason"] is None for row in run["rows"])
    assert isinstance(rows["a"]["result"]["總分"], int)
    assert list(rows["a"]["result"]["維度"]) == ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準"]
    assert rows["c"]["result"]["淘汰"] is True
    assert rows["c"]["result"]["總分"] is None
    assert rows["c"]["result"]["淘汰原因"] == ["職稱含排除關鍵字：業務"]


def test_failure_does_not_stop(client, five_listed, fake_llm):
    fake_llm.behaviors = {"丁職缺": "llm_error"}

    run = _run(client, five_listed, _drafts(client.app.state.db_path))

    assert [row["status"] for row in run["rows"]] == ["done", "done", "done", "failed", "done"]
    assert (run["rows"][3]["reason"], run["rows"][3]["result"]) == ("模擬的 API 錯誤", None)
    assert run["done"] == 5


def test_running_state_and_stop(client, five_listed, fake_llm):
    # 評第 3 筆時看得到已完成的結果；停止後第 4、5 筆標成沒試跑
    fake_llm.hold("丙職缺")
    response = _start(client, five_listed, _drafts(client.app.state.db_path))
    state = _wait_state(client, lambda s: s["running"] and s["running"]["done"] == 2)

    running = state["running"]
    assert [row["status"] for row in running["rows"]] == ["done", "done", "scoring", "queued", "queued"]
    assert running["rows"][0]["result"] is not None
    assert (running["stopping"], state["busy"]) == (False, None)

    assert client.post("/api/dry-run/stop").status_code == 204
    assert client.get("/api/dry-run").json()["running"]["stopping"] is True
    fake_llm.release("丙職缺")
    last = _wait_state(client, lambda s: s["running"] is None)["last"]

    assert last["id"] == response.json()["run_id"]
    assert [row["status"] for row in last["rows"]] == ["done", "done", "done", "skipped", "skipped"]
    assert (last["done"], last["stopped"]) == (3, True)


def test_client_error_scores_nothing(client, three_listed, monkeypatch):
    def broken(provider, model):
        raise LLMError("連不上")

    monkeypatch.setattr("web.dry_run.get_client", broken)

    run = _run(client, three_listed, _drafts(client.app.state.db_path))

    assert run["error"] == "無法開始試跑：連不上"
    assert [row["status"] for row in run["rows"]] == ["skipped"] * 3
    assert (run["done"], run["stopped"]) == (0, True)


def test_unexpected_error_fails_current(client, five_listed, monkeypatch):
    # 其他錯誤讓試跑停止：正在試跑的那一筆算失敗，之後的標成沒試跑
    import job_scoring.batch as batch
    real_score = batch.score_and_save

    def broken_score(job, *args):
        if job["職缺代碼"] == "j3":
            raise KeyError("壞掉的欄位")
        return real_score(job, *args)

    monkeypatch.setattr(batch, "score_and_save", broken_score)
    # 背景執行緒的例外往外拋時，pytest 會提醒；這裡是預期中的
    monkeypatch.setattr("threading.excepthook", lambda args: None)

    run = _run(client, five_listed, _drafts(client.app.state.db_path))
    # 例外在結果交出之後才送到 excepthook：等執行緒結束，換掉的 excepthook 才確定收得到
    for thread in threading.enumerate():
        if thread.name == "job-試跑":
            thread.join(timeout=10)

    assert run["error"].startswith("試跑中發生錯誤，已停止：")
    assert [row["status"] for row in run["rows"]] == ["done", "done", "failed", "skipped", "skipped"]
    assert run["rows"][2]["reason"].startswith("試跑中發生錯誤：")
    assert (run["done"], run["stopped"]) == (3, True)


def test_next_run_replaces_last(client, three_listed):
    drafts = _drafts(client.app.state.db_path)
    first = _run(client, ["a"], drafts)
    second = _run(client, ["b"], drafts)

    assert second["id"] == first["id"] + 1
    assert client.get("/api/dry-run").json()["last"]["id"] == second["id"]
