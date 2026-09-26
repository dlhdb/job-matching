"""網頁後端：評分的 API。LLM 換成 fake_llm，資料庫是 scoring_db（偏好與經歷已換成測試用的內容）。"""

import json
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from job_db import list_current_scores, list_scores, open_db, save_auto_score, save_run
from job_scoring.llm import DEFAULT_MODEL, MODELS
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


@pytest.fixture
def five_jobs(make_job):
    """正常、會被淘汰、正常、會評分失敗、正常；存入的順序和職缺表的順序不同"""
    return [
        make_job(**{"職缺代碼": "j1", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "j2", "職缺名稱": "業務專員"}),
        make_job(**{"職缺代碼": "j3", "職缺名稱": "丙職缺"}),
        make_job(**{"職缺代碼": "j4", "職缺名稱": "丁職缺"}),
        make_job(**{"職缺代碼": "j5", "職缺名稱": "戊職缺"}),
    ]


def _seed(db_path, jobs):
    with closing(open_db(db_path)) as conn:
        save_run(conn, list(reversed(jobs)), T, "爬蟲")


DIMENSION_SCORES = {"職涯方向契合度": 4, "技能匹配度": None, "產業公司吸引力": 3, "薪資水準": 4}


def _details(job_no, total, eliminated):
    """符合評分結果格式的評分明細"""
    return {
        "職缺代碼": job_no, "淘汰": eliminated, "淘汰原因": ["職稱含排除關鍵字：業務"] if eliminated else [],
        "維度": None if eliminated else {name: {"分數": s, "理由": f"{name}的理由"} for name, s in DIMENSION_SCORES.items()},
        "總分": total, "未知維度": [] if eliminated else ["技能匹配度"], "評語": "舊評語",
    }


def _write_score(db_path, job_no, total=60, scored_at=T, basis=True, eliminated=False):
    """直接寫入一筆評分紀錄；basis 為 False 時是記錄依據之前的評分"""
    total = None if eliminated else total
    details = _details(job_no, total, eliminated)
    with closing(open_db(db_path)) as conn:
        if basis:
            save_auto_score(
                conn, job_no=job_no, scored_at=scored_at, eliminated=eliminated, total=total, comment="舊評語",
                details=details, provider=None if eliminated else "gemini", model=None if eliminated else "舊模型",
                basis={"偏好版本": 2, "經歷版本": 2, "模板版本": 1, "職缺快照": {"職缺名稱": "舊"}},
            )
        else:
            with conn:
                conn.execute(
                    'INSERT INTO job_scores ("職缺代碼", "評分時間", "淘汰", "總分", "評語", "評分明細") '
                    "VALUES (?, ?, 0, ?, '舊評語', ?)",
                    (job_no, scored_at.isoformat(), total, json.dumps(details, ensure_ascii=False)),
                )


def _records(db_path, job_no):
    with closing(open_db(db_path)) as conn:
        return list_scores(conn, job_no)


def _plan(client, codes, rescore=False):
    response = client.post("/api/scoring/plan", json={"codes": codes, "rescore": rescore})
    assert response.status_code == 200
    return response.json()


def _start(client, codes, rescore=False, model=DEFAULT_MODEL):
    return client.post("/api/scoring", json={"codes": codes, "rescore": rescore, "model": model})


def _wait_state(client, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get("/api/scoring").json()
        if predicate(state):
            return state
        time.sleep(0.02)
    pytest.fail(f"等不到預期的評分狀態：{state}")


def _run(client, codes, **kwargs):
    """送去評分並等到結束，回傳這次的結果"""
    response = _start(client, codes, **kwargs)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    state = _wait_state(client, lambda s: s["running"] is None and s["last"] and s["last"]["id"] == run_id)
    return state["last"]


# ---------------------------------------------------------------------------
# 送出前的確認
# ---------------------------------------------------------------------------

@pytest.fixture
def four_selected(scoring_db, make_job):
    """勾選 4 筆：a、b 已評過；c 沒評過；d 沒評過、會被淘汰"""
    jobs = [make_job(職缺代碼=code) for code in "abc"] + [make_job(職缺代碼="d", 職缺名稱="業務專員")]
    _seed(scoring_db, jobs)
    _write_score(scoring_db, "a")
    _write_score(scoring_db, "b")
    return ["a", "b", "c", "d"]


def test_plan_counts(client, four_selected):
    # AC-score-confirm (a)
    plan = _plan(client, four_selected)

    assert (plan["selected"], plan["scored"], plan["targets"], plan["eliminated"]) == (4, 2, 2, 1)
    assert plan["versions"] == {
        "preferences": {"version": 2, "name": "測試偏好"},
        "experience": {"version": 2, "name": "測試經歷"},
        "template": {"version": 1, "name": "預設模板"},
    }
    assert (plan["provider"], plan["models"]) == ("gemini", MODELS["gemini"])
    assert plan["models"][0] == DEFAULT_MODEL
    assert plan["errors"] == []


def test_plan_rescore_counts(client, four_selected):
    # AC-rescore：勾重評時將評的筆數跟著變
    plan = _plan(client, four_selected, rescore=True)

    assert (plan["targets"], plan["eliminated"]) == (4, 1)


def test_plan_no_api_key(client, four_selected, monkeypatch):
    # AC-score-confirm (c)、(d)
    monkeypatch.delenv("GEMINI_API_KEY")

    [error] = _plan(client, four_selected)["errors"]
    assert "API key" in error
    assert _plan(client, ["d"])["errors"] == []


def test_no_api_key_eliminated_only_scores(client, four_selected, monkeypatch, fake_llm):
    # AC-filter-no-key：只有會被淘汰的職缺時不需要 API key
    monkeypatch.delenv("GEMINI_API_KEY")

    run = _run(client, ["d"])

    assert (run["eliminated"], run["failed"], run["error"]) == (1, 0, None)
    [record] = _records(client.app.state.db_path, "d")
    assert record["評分明細"]["淘汰"] is True
    assert record["評分明細"]["淘汰原因"]
    assert fake_llm.models == []


def test_plan_zero_targets(client, four_selected):
    # AC-score-confirm (e)
    plan = _plan(client, ["a", "b"])

    assert plan["targets"] == 0
    assert [e for e in plan["errors"] if "將評 0 筆" in e]


def test_plan_default_experience(client, four_selected):
    # AC-score-confirm (f)
    client.put("/api/settings/experience/current", json={"version": 1})

    [error] = _plan(client, four_selected)["errors"]
    assert "經歷還是預設範例" in error


def test_plan_default_preferences(client, four_selected):
    client.put("/api/settings/preferences/current", json={"version": 1})

    [error] = _plan(client, four_selected)["errors"]
    assert "偏好還是預設範例" in error


def test_plan_invalid_preferences(client, four_selected):
    with closing(open_db(client.app.state.db_path)) as conn, conn:
        conn.execute("INSERT INTO settings_versions VALUES ('preferences', 3, '壞掉的', '', '2026-09-20T10:00:00', '- 清單')")
        conn.execute("UPDATE current_settings SET \"版本\" = 3 WHERE \"種類\" = 'preferences'")

    plan = _plan(client, four_selected)

    assert plan["eliminated"] is None
    assert [e for e in plan["errors"] if e.startswith("目前設定有錯")]


def test_plan_unknown_code(client, four_selected):
    [error] = _plan(client, ["c", "沒有這筆"])["errors"]
    assert "不在職缺資料庫" in error


def test_plan_and_start_while_other_job_running(client, four_selected):
    release = threading.Event()
    client.app.state.runner.start("抓取", lambda job: release.wait(10))
    try:
        assert "目前正在抓取" in _plan(client, four_selected)["errors"][-1]
        response = _start(client, four_selected)
        assert response.status_code == 409
        assert client.get("/api/scoring").json()["busy"] == "抓取"
    finally:
        release.set()


def test_start_rechecks_and_rejects(client, four_selected):
    # 開始時重讀設定、重做檢查：確認視窗開著時改回預設範例，按開始就擋下
    assert _plan(client, four_selected)["errors"] == []
    client.put("/api/settings/experience/current", json={"version": 1})

    response = _start(client, four_selected)

    assert response.status_code == 422
    assert "經歷還是預設範例" in response.json()["detail"][0]
    assert client.get("/api/scoring").json() == {"running": None, "last": None, "busy": None}
    assert _records(client.app.state.db_path, "c") == []


def test_start_unknown_model(client, four_selected):
    response = _start(client, four_selected, model="不存在的模型")

    assert response.status_code == 422
    assert response.json()["detail"] == ["不認得的模型：不存在的模型"]


# ---------------------------------------------------------------------------
# 評分作業
# ---------------------------------------------------------------------------

def test_order_failure_and_summary(client, five_jobs, fake_llm):
    # AC-score-order、AC-score-failure、AC-score-store、AC-score-run (c) 的計數
    _seed(client.app.state.db_path, five_jobs)
    fake_llm.behaviors = {"丁職缺": "llm_error"}
    codes = ["j1", "j2", "j3", "j4", "j5"]

    run = _run(client, codes)

    assert fake_llm.calls("甲職缺", "丙職缺", "丁職缺", "戊職缺") == ["甲職缺", "丙職缺", "丁職缺", "戊職缺"]
    assert (run["total"], run["done"], run["ok"], run["eliminated"], run["failed"], run["skipped"]) == (5, 5, 3, 1, 1, 0)
    assert (run["stopped"], run["error"]) == (False, None)
    assert run["statuses"] == [{"code": "j4", "status": "failed", "reason": "模擬的 API 錯誤"}]
    db_path = client.app.state.db_path
    assert _records(db_path, "j4") == []
    [kept] = _records(db_path, "j1")
    assert kept["總分"] is not None and kept["評分明細"]["總分"] == kept["總分"]
    [out] = _records(db_path, "j2")
    assert (out["淘汰"], out["總分"], out["評分明細"]["淘汰"]) == (1, None, True)


def test_eliminated_comment(client, make_job):
    # AC-filter-comment：同時符合兩條淘汰條件
    _seed(client.app.state.db_path, [make_job(職缺代碼="x", 職缺名稱="業務專員", 公司名稱="乙公司")])

    _run(client, ["x"])

    [record] = _records(client.app.state.db_path, "x")
    assert record["評語"] == "淘汰：公司在排除名單：乙公司；職稱含排除關鍵字：業務"
    assert record["總分"] is None


def test_running_state(client, five_jobs, fake_llm):
    # AC-score-run (a) 的資料部分：排隊中、評分中與進度
    _seed(client.app.state.db_path, five_jobs)
    fake_llm.hold("丙職缺")
    _start(client, ["j1", "j2", "j3", "j4", "j5"])

    state = _wait_state(client, lambda s: s["running"] and s["running"]["done"] == 2)

    running = state["running"]
    assert (running["total"], running["stopping"]) == (5, False)
    assert running["statuses"] == [
        {"code": "j3", "status": "scoring", "reason": None},
        {"code": "j4", "status": "queued", "reason": None},
        {"code": "j5", "status": "queued", "reason": None},
    ]
    assert state["busy"] is None
    fake_llm.release("丙職缺")


def test_stop(client, five_jobs, fake_llm):
    # AC-score-run (b)：評第 3 筆時停止，第 4、5 筆不評
    _seed(client.app.state.db_path, five_jobs)
    fake_llm.hold("丙職缺")
    response = _start(client, ["j1", "j2", "j3", "j4", "j5"])
    _wait_state(client, lambda s: s["running"] and s["running"]["done"] == 2)

    assert client.post("/api/scoring/stop").status_code == 204
    assert client.get("/api/scoring").json()["running"]["stopping"] is True
    fake_llm.release("丙職缺")
    state = _wait_state(client, lambda s: s["running"] is None)

    last = state["last"]
    assert last["id"] == response.json()["run_id"]
    assert (last["done"], last["ok"], last["eliminated"], last["failed"], last["skipped"]) == (3, 2, 1, 0, 2)
    assert (last["stopped"], last["statuses"]) == (True, [])
    db_path = client.app.state.db_path
    assert _records(db_path, "j4") == [] and _records(db_path, "j5") == []


def test_settings_read_at_start(client, make_job, fake_llm, preferences_data):
    # AC-score-settings：評第一筆時套用第 3 版，兩筆都用第 2 版
    _seed(client.app.state.db_path, [make_job(職缺代碼="a", 職缺名稱="甲職缺"), make_job(職缺代碼="b", 職缺名稱="乙職缺")])
    preferences_data["權重"] = {"職涯方向契合度": 1, "技能匹配度": 0, "產業公司吸引力": 0, "薪資水準": 0}
    v3 = yaml.safe_dump(preferences_data, allow_unicode=True)
    fake_llm.hold("甲職缺")

    _start(client, ["a", "b"])
    _wait_state(client, lambda s: s["running"] and s["running"]["statuses"][0]["status"] == "scoring")
    assert client.post("/api/settings/preferences/versions", json={"name": "第 3 版", "content": v3}).status_code == 201
    fake_llm.release("甲職缺")
    _wait_state(client, lambda s: s["running"] is None)

    db_path = client.app.state.db_path
    for code in "ab":
        [record] = _records(db_path, code)
        assert record["偏好版本"] == 2
        # 第 2 版的權重：職涯 5、技能 3（未知）、產業 3、薪資 4 → 75
        assert record["總分"] == 75
    # 之後再送出的評分才用第 3 版
    _run(client, ["a"], rescore=True)
    newest = _records(db_path, "a")[0]
    assert (newest["偏好版本"], newest["總分"]) == (3, 100)


def test_selected_model_recorded(client, make_job, fake_llm):
    # AC-score-confirm (b)
    _seed(client.app.state.db_path, [make_job(職缺代碼="a")])
    model = MODELS["gemini"][1]

    _run(client, ["a"], model=model)

    assert fake_llm.models == [model]
    assert _records(client.app.state.db_path, "a")[0]["模型"] == model


def test_rescore(client, make_job, fake_llm):
    # AC-rescore
    _seed(client.app.state.db_path, [make_job(職缺代碼=code, 職缺名稱=f"{code}職缺") for code in "abc"])
    _write_score(client.app.state.db_path, "a")
    db_path = client.app.state.db_path

    _run(client, ["a", "b", "c"])
    assert len(fake_llm.prompts) == 2
    assert len(_records(db_path, "a")) == 1

    _run(client, ["a", "b", "c"], rescore=True)
    assert len(fake_llm.prompts) == 5
    assert [r["評語"] for r in _records(db_path, "a")] == ["總評", "舊評語"]


def test_rescore_failure_keeps_score(client, make_job, fake_llm):
    # AC-rescore-failure
    _seed(client.app.state.db_path, [make_job(職缺代碼="a", 職缺名稱="甲職缺")])
    _write_score(client.app.state.db_path, "a", total=60)
    fake_llm.behaviors = {"甲職缺": "llm_error"}

    run = _run(client, ["a"], rescore=True)

    assert run["failed"] == 1
    assert run["statuses"][0]["status"] == "failed"
    [current] = client.get("/api/scores").json()["scores"]
    assert (current["總分"], current["評語"]) == (60, "舊評語")
    assert len(_records(client.app.state.db_path, "a")) == 1


def test_history_append(client, make_job, fake_llm, preferences_data):
    # AC-history-append
    _seed(client.app.state.db_path, [make_job(職缺代碼="a")])
    db_path = client.app.state.db_path

    _run(client, ["a"])
    _run(client, ["a"], rescore=True)
    assert len(fake_llm.prompts) == 2
    first_two = _records(db_path, "a")
    assert len(first_two) == 2

    preferences_data["權重"]["職涯方向契合度"] = 2
    client.post("/api/settings/preferences/versions", json={"name": "改權重", "content": yaml.safe_dump(preferences_data, allow_unicode=True)})
    _run(client, ["a"], rescore=True)

    records = _records(db_path, "a")
    assert len(records) == 3
    assert records[0]["總分"] != records[1]["總分"]
    assert records[1:] == first_two


def test_write_failure_stops(client, five_jobs, monkeypatch):
    # 中途無法寫入資料庫：那一筆算失敗，停止，已寫入的留著
    _seed(client.app.state.db_path, five_jobs)
    import job_scoring.scorer as scorer
    real_save = scorer.save_auto_score
    calls = []

    def flaky_save(conn, **kwargs):
        calls.append(kwargs["job_no"])
        if len(calls) == 2:
            raise sqlite3.OperationalError("disk I/O error")
        real_save(conn, **kwargs)

    monkeypatch.setattr(scorer, "save_auto_score", flaky_save)

    run = _run(client, ["j1", "j2", "j3", "j4", "j5"])

    assert run["error"] == "無法寫入資料庫，已停止：disk I/O error"
    assert (run["done"], run["ok"], run["failed"], run["skipped"], run["stopped"]) == (2, 1, 1, 3, True)
    assert run["statuses"] == [{"code": "j2", "status": "failed", "reason": "寫入資料庫失敗：disk I/O error"}]
    db_path = client.app.state.db_path
    assert len(_records(db_path, "j1")) == 1
    assert _records(db_path, "j3") == []


def test_unexpected_error_fails_current(client, five_jobs, monkeypatch):
    # 其他錯誤同樣讓評分停止：正在評的那一筆算失敗，不算沒評
    _seed(client.app.state.db_path, five_jobs)
    import job_scoring.scorer as scorer
    real_save = scorer.save_auto_score

    def broken_save(conn, **kwargs):
        if kwargs["job_no"] == "j3":
            raise KeyError("壞掉的欄位")
        real_save(conn, **kwargs)

    monkeypatch.setattr(scorer, "save_auto_score", broken_save)
    # 背景執行緒的例外往外拋時，pytest 會提醒；這裡是預期中的
    monkeypatch.setattr("threading.excepthook", lambda args: None)

    run = _run(client, ["j1", "j2", "j3", "j4", "j5"])

    assert run["error"].startswith("評分中發生錯誤，已停止：")
    assert (run["done"], run["failed"], run["skipped"], run["stopped"]) == (3, 1, 2, True)
    assert run["statuses"][0]["code"] == "j3"


def test_client_error_scores_nothing(client, make_job, fake_llm, monkeypatch):
    from job_scoring.llm import LLMError

    def broken(provider, model):
        raise LLMError("連不上")

    monkeypatch.setattr("web.scoring.get_client", broken)
    _seed(client.app.state.db_path, [make_job(職缺代碼="a")])

    run = _run(client, ["a"])

    assert run["error"] == "無法開始評分：連不上"
    assert (run["done"], run["skipped"], run["stopped"]) == (0, 1, True)
    assert _records(client.app.state.db_path, "a") == []


# ---------------------------------------------------------------------------
# 評分的欄位與展開列
# ---------------------------------------------------------------------------

def test_scores_current(client, make_job):
    # AC-history-current、AC-rank-columns 的資料部分
    db_path = client.app.state.db_path
    _seed(db_path, [make_job(職缺代碼=code) for code in "ABC"])
    _write_score(db_path, "A", total=60, scored_at=datetime(2026, 9, 1, 9, 0, 0))
    _write_score(db_path, "A", total=80, scored_at=datetime(2026, 9, 2, 9, 0, 0))
    # B 的兩筆評分時間相同：後寫入的那筆被淘汰
    _write_score(db_path, "B", total=50, scored_at=datetime(2026, 9, 3, 9, 0, 0))
    _write_score(db_path, "B", scored_at=datetime(2026, 9, 3, 9, 0, 0), eliminated=True)

    scores = {s["職缺代碼"]: s for s in client.get("/api/scores").json()["scores"]}

    assert set(scores) == {"A", "B"}
    assert (scores["A"]["總分"], scores["A"]["維度分數"]) == (80, DIMENSION_SCORES)
    assert (scores["A"]["供應商"], scores["A"]["模型"], scores["A"]["評分時間"]) == ("gemini", "舊模型", "2026-09-02T09:00:00")
    assert (scores["B"]["淘汰"], scores["B"]["總分"], scores["B"]["維度分數"]) == (True, None, None)


def test_scores_eliminated_has_no_dimensions(client, make_job):
    _seed(client.app.state.db_path, [make_job(職缺代碼="x", 職缺名稱="業務專員")])
    _run(client, ["x"])

    [score] = client.get("/api/scores").json()["scores"]
    assert (score["淘汰"], score["維度分數"], score["供應商"], score["模型"]) == (True, None, None, None)


def test_history_basis(client, make_job, preferences_data):
    # AC-basis (a)、(b) 的資料部分：之後職缺內容更新、偏好換成第 3 版，依據仍是評分當時的
    db_path = client.app.state.db_path
    _seed(db_path, [make_job(職缺代碼="a", 工作內容="評分當時的工作內容"), make_job(職缺代碼="b", 職缺名稱="業務專員")])
    _run(client, ["a", "b"])
    _seed(db_path, [make_job(職缺代碼="a", 工作內容="更新後的工作內容")])
    preferences_data["目標方向"] = ["第 3 版的方向"]
    client.post("/api/settings/preferences/versions", json={"name": "第 3 版", "content": yaml.safe_dump(preferences_data, allow_unicode=True)})

    [a] = client.get("/api/scores/a").json()["records"]
    basis = a["basis"]
    assert (basis["preferences"]["version"], basis["preferences"]["name"]) == (2, "測試偏好")
    assert (basis["experience"]["version"], basis["experience"]["content"]) == (2, "經歷標記-BBB")
    assert basis["template"]["version"] == 1
    assert basis["snapshot"]["工作內容"] == "評分當時的工作內容"
    user = basis["prompt"]["user"]
    assert "評分當時的工作內容" in user and "更新後的工作內容" not in user
    assert "目標標記-AAA" in basis["prompt"]["system"] + user
    assert "第 3 版的方向" not in basis["prompt"]["system"] + user
    assert basis["prompt_error"] is None

    # AC-basis (c)：被淘汰的沒有提示詞，快照裡有淘汰依據的欄位
    [b] = client.get("/api/scores/b").json()["records"]
    assert (b["basis"]["prompt"], b["basis"]["prompt_error"]) == (None, None)
    assert b["basis"]["snapshot"]["職缺名稱"] == "業務專員"


def test_history_order_and_legacy(client, make_job):
    # AC-history-all 的資料部分、AC-basis-legacy
    db_path = client.app.state.db_path
    _seed(db_path, [make_job(職缺代碼="a")])
    _write_score(db_path, "a", total=60, scored_at=datetime(2026, 9, 1, 9, 0, 0), basis=False)
    _write_score(db_path, "a", total=70, scored_at=datetime(2026, 9, 2, 9, 0, 0))
    _write_score(db_path, "a", total=80, scored_at=datetime(2026, 9, 2, 9, 0, 0))

    records = client.get("/api/scores/a").json()["records"]

    assert [r["總分"] for r in records] == [80, 70, 60]
    assert records[2]["basis"] is None
    assert client.get("/api/scores/沒有這筆").json() == {"records": []}


def test_history_prompt_error(client, make_job):
    # 紀錄指向的偏好版本不符合現在的規則時，組不回提示詞並說明原因
    db_path = client.app.state.db_path
    _seed(db_path, [make_job(職缺代碼="a")])
    with closing(open_db(db_path)) as conn, conn:
        conn.execute("INSERT INTO settings_versions VALUES ('preferences', 3, '壞掉的', '', '2026-09-20T10:00:00', '- 清單')")
    with closing(open_db(db_path)) as conn:
        save_auto_score(
            conn, job_no="a", scored_at=T, eliminated=False, total=60, comment="評語", details=_details("a", 60, False),
            provider="gemini", model="m", basis={"偏好版本": 3, "經歷版本": 2, "模板版本": 1, "職缺快照": {"職缺名稱": "a"}},
        )

    [record] = client.get("/api/scores/a").json()["records"]

    assert record["basis"]["prompt"] is None
    assert "組不回提示詞" in record["basis"]["prompt_error"]


def test_scores_empty(client):
    assert client.get("/api/scores").json() == {"scores": []}
    with closing(open_db(client.app.state.db_path)) as conn:
        assert list_current_scores(conn) == []
