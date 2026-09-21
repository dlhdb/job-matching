"""整批評分（job_scoring.batch）的測試：逐筆評分、單筆失敗不中斷、結果寫入資料庫、結果檔。"""

import csv
import json
import re
from datetime import datetime

import pytest

from job_db import get_score_details, list_scored_jobs, save_auto_score, save_score
from job_scoring.batch import score_batch, write_results
from job_scoring.models import DIMENSIONS

JSON_KEYS = [
    "職缺代碼", "職缺名稱", "公司名稱", "薪資待遇", "職缺連結",
    "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語", "失敗原因",
]
CSV_HEADER = [
    "職缺代碼", "職缺名稱", "公司名稱", "薪資待遇",
    "總分", *DIMENSIONS,
    "未知維度", "淘汰原因", "評語", "失敗原因", "職缺連結",
]


def _no_progress(message):
    pass


def _store(conn):
    """
    score_batch 寫入資料庫需要的參數

    :return: dict, conn、provider、model
    """
    return {"conn": conn, "provider": "gemini", "model": "測試模型"}


@pytest.fixture
def five_jobs(make_job):
    """正常、會被淘汰、正常、會評分失敗、正常"""
    return [
        make_job(**{"職缺代碼": "j1", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "j2", "職缺名稱": "業務專員", "公司名稱": "乙公司"}),
        make_job(**{"職缺代碼": "j3", "職缺名稱": "丙職缺"}),
        make_job(**{"職缺代碼": "j4", "職缺名稱": "丁職缺"}),
        make_job(**{"職缺代碼": "j5", "職缺名稱": "戊職缺"}),
    ]


@pytest.fixture
def five_results(five_jobs, prefs, make_batch_client, db_conn):
    """
    五筆職缺的整批結果與使用的假 client

    :return: tuple (list[BatchResult], BatchFakeLLMClient)
    """
    client = make_batch_client({
        "甲職缺": {"career": 5, "skill": 5, "industry": 5},
        "丙職缺": {"career": 1, "skill": 1, "industry": 1},
        "丁職缺": "llm_error",
        "戊職缺": {},
    })
    return score_batch(five_jobs, prefs, "經歷", lambda: client, _no_progress, **_store(db_conn)), client


def test_score_batch_scoring_order_and_calls(five_results):
    results, client = five_results

    assert [r.job_no for r in results] == ["j1", "j2", "j3", "j4", "j5"]
    assert len(client.calls) == 4
    assert "業務專員" not in client.calls
    assert results[1].eliminated is True
    assert results[1].failure is None
    for i in (0, 2, 4):
        assert results[i].failure is None
        assert results[i].total is not None
    assert results[0].total > results[2].total


def test_score_batch_failure_does_not_stop(make_job, prefs, make_batch_client, db_conn):
    jobs = [
        make_job(**{"職缺代碼": "a", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "b", "職缺名稱": "乙職缺"}),
        make_job(**{"職缺代碼": "c", "職缺名稱": "丙職缺"}),
    ]
    client = make_batch_client({"甲職缺": "llm_error", "乙職缺": "invalid", "丙職缺": {}})

    results = score_batch(jobs, prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))

    for r in results[:2]:
        assert r.failure
        assert r.total is None
        assert r.dimensions is None
        assert r.comment is None
        assert r.eliminated is False
        assert r.elimination_reasons == []
        assert r.unknown_dimensions == []
    assert results[2].failure is None
    assert results[2].total == 75


def test_score_batch_client_created_lazily(out_job, prefs, db_conn):
    def _factory():
        pytest.fail("全部被淘汰時不應建立 client")

    progress = []
    results = score_batch([out_job, out_job], prefs, "經歷", _factory, progress.append, **_store(db_conn))

    assert all(r.eliminated for r in results)
    assert progress[1].startswith("⏳ [i] (2/2) 業務專員 - 甲公司")


def _score_rows(conn):
    """
    以職缺代碼為鍵取出 job_scores 表，同一筆職缺有多筆時取最新寫入的一筆

    :return: dict[str, dict]
    """
    cursor = conn.execute('SELECT * FROM job_scores ORDER BY "評分編號"')
    names = [d[0] for d in cursor.description]
    return {row["職缺代碼"]: row for row in (dict(zip(names, values)) for values in cursor)}


def test_score_batch_store_write(make_job, prefs, make_batch_client, db_conn):
    jobs = [
        make_job(**{"職缺代碼": "a", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "b", "職缺名稱": "業務專員"}),
        make_job(**{"職缺代碼": "c", "職缺名稱": "丙職缺"}),
    ]
    save_auto_score(
        db_conn, job_no="c", scored_at=datetime(2026, 9, 1, 10, 0, 0), eliminated=False, total=60,
        comment="舊評語", details={"職缺代碼": "c", "總分": 60}, cache_key="舊鍵", provider="gemini", model="舊模型",
    )
    old_row = _score_rows(db_conn)["c"]
    client = make_batch_client({"甲職缺": {}, "丙職缺": "llm_error"})

    results = score_batch(jobs, prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))
    rows = _score_rows(db_conn)

    assert set(rows) == {"a", "b", "c"}
    for job_no, result in (("a", results[0]), ("b", results[1])):
        row = rows[job_no]
        stored = json.loads(row["評分明細"])
        assert list(stored) == ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]
        assert stored["職缺代碼"] == job_no
        assert row["淘汰"] == int(stored["淘汰"])
        assert row["總分"] == stored["總分"] == result.total
        assert row["評語"] == stored["評語"] == result.comment
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", row["評分時間"])

    assert rows["a"]["淘汰"] == 0
    assert rows["a"]["總分"] == 75
    assert re.fullmatch(r"[0-9a-f]{64}", rows["a"]["快取鍵"])
    assert (rows["a"]["供應商"], rows["a"]["模型"]) == ("gemini", "測試模型")

    assert rows["b"]["淘汰"] == 1
    assert rows["b"]["總分"] is None
    assert rows["b"]["快取鍵"] is None
    assert json.loads(rows["b"]["評分明細"])["淘汰原因"]

    assert results[2].failure
    assert rows["c"] == old_row


def test_get_score_details_returns_stored_result(make_job, prefs, make_batch_client, db_conn):
    jobs = [make_job(**{"職缺代碼": "a", "職缺名稱": "甲職缺"})]
    client = make_batch_client({"甲職缺": {}})
    results = score_batch(jobs, prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))

    stored = get_score_details(db_conn, "a")

    assert list(stored) == ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]
    assert list(stored["維度"]) == list(DIMENSIONS)
    assert all(dim["理由"] for dim in stored["維度"].values())
    assert (stored["總分"], stored["評語"]) == (results[0].total, results[0].comment)


def test_get_score_details_missing_is_none(db_conn):
    assert get_score_details(db_conn, "沒有這筆") is None


def test_get_score_details_manual_only_is_none(db_conn):
    save_score(db_conn, job_no="a", comment="手動的評語", total=70)

    # 只有手動評分、沒有自動評分的結果，視為查不到
    assert get_score_details(db_conn, "a") is None


def test_list_scored_jobs_adds_provider_and_model(make_job, prefs, make_batch_client, db_conn):
    jobs = [
        make_job(**{"職缺代碼": "a", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "b", "職缺名稱": "業務專員"}),
    ]
    client = make_batch_client({"甲職缺": {}})
    score_batch(jobs, prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))

    rows = {row["職缺代碼"]: row for row in list_scored_jobs(db_conn)}

    assert (rows["a"]["供應商"], rows["a"]["模型"]) == ("gemini", "測試模型")
    assert (rows["b"]["供應商"], rows["b"]["模型"]) == (None, None)
    assert all("評分明細" not in row for row in rows.values())


def test_write_results_output_files(five_results, tmp_path):
    results, _ = five_results
    input_path = tmp_path / "input" / "jobs_104_測試_20260101_000000.json"

    json_path, csv_path = write_results(results, input_path, tmp_path / "scores")

    assert json_path == tmp_path / "scores" / "jobs_104_測試_20260101_000000_scored.json"
    assert csv_path == tmp_path / "scores" / "jobs_104_測試_20260101_000000_scored.csv"

    records = json.loads(json_path.read_text(encoding="utf-8"))
    assert all(list(record) == JSON_KEYS for record in records)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == CSV_HEADER
    assert [row["職缺代碼"] for row in rows] == [record["職缺代碼"] for record in records]

    # 第 5 筆的技能匹配度為 null；第 4 筆評分失敗，所有分數欄都是空的
    assert rows[4]["技能匹配度"] == ""
    assert rows[4]["薪資水準"] == "4"
    assert rows[4]["未知維度"] == "技能匹配度"
    assert all(rows[3][name] == "" for name in ["總分", *DIMENSIONS])
    assert rows[3]["失敗原因"]
    # 被淘汰的那列收集了多條原因，以 ", " 合併
    assert rows[1]["淘汰原因"] == ", ".join(records[1]["淘汰原因"])
    assert len(records[1]["淘汰原因"]) == 2


def test_score_batch_filter_comment(make_job, prefs, db_conn, tmp_path):
    # 同時符合公司與職稱兩條淘汰條件
    job = make_job(**{"職缺代碼": "out", "職缺名稱": "業務專員", "公司名稱": "乙公司"})

    [result] = score_batch([job], prefs, "經歷", lambda: None, _no_progress, **_store(db_conn))
    json_path, csv_path = write_results([result], tmp_path / "jobs.json", tmp_path / "scores")

    expected = "淘汰：公司在排除名單：乙公司；職稱含排除關鍵字：業務"
    assert result.comment == expected
    assert result.total is None
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["評語"] == expected
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        assert next(csv.DictReader(f))["評語"] == expected
    row = _score_rows(db_conn)["out"]
    assert row["評語"] == json.loads(row["評分明細"])["評語"] == expected


def _records(conn, job_no):
    """
    取出一筆職缺的所有評分紀錄，依寫入順序

    :return: list[dict]
    """
    cursor = conn.execute('SELECT * FROM job_scores WHERE "職缺代碼" = ? ORDER BY "評分編號"', (job_no,))
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, values)) for values in cursor]


def test_score_batch_history_source(ok_job, out_job, prefs, make_batch_client, db_conn):
    score_batch([ok_job, out_job], prefs, "經歷", lambda: make_batch_client({}), _no_progress, **_store(db_conn))
    save_score(db_conn, job_no="ok", comment="手動的評語", total=90)

    auto_ok, manual_ok = _records(db_conn, "ok")
    [auto_out] = _records(db_conn, "out")

    assert (auto_ok["評分來源"], auto_ok["供應商"], auto_ok["模型"]) == ("auto", "gemini", "測試模型")
    assert (auto_out["評分來源"], auto_out["供應商"], auto_out["模型"]) == ("auto", None, None)
    assert (manual_ok["評分來源"], manual_ok["供應商"], manual_ok["模型"]) == ("manual", None, None)


def test_score_batch_history_append(ok_job, prefs, make_batch_client, db_conn):
    client = make_batch_client({})

    # (a) 職缺與設定都不變，第二次和最新一筆相同，不新增
    score_batch([ok_job], prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))
    score_batch([ok_job], prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))
    [first] = _records(db_conn, "ok")

    # (b) 權重改變讓總分不同，新增一筆
    weights = {"職涯方向契合度": 0.1, "技能匹配度": 0.1, "產業公司吸引力": 0.1, "薪資水準": 0.7}
    new_prefs = prefs.model_copy(update={"weights": weights})
    score_batch([ok_job], new_prefs, "經歷", lambda: client, _no_progress, **_store(db_conn))
    records = _records(db_conn, "ok")

    assert first["評分來源"] == "auto"
    assert len(records) == 2
    assert records[0] == first
    assert records[1]["評分來源"] == "auto"
    assert records[1]["總分"] != first["總分"]
    assert len(client.calls) == 1


def test_score_batch_history_coexist(ok_job, prefs, make_batch_client, db_conn):
    score_batch([ok_job], prefs, "經歷", lambda: make_batch_client({}), _no_progress, **_store(db_conn))
    [auto] = _records(db_conn, "ok")

    # (a) 手動評分不覆寫自動評分
    save_score(db_conn, job_no="ok", comment="手動的評語", total=90)
    after_manual = _records(db_conn, "ok")

    # (b) 換了經歷，AI 給出不同的評語，自動評分不覆寫手動評分
    client = make_batch_client({"Python 工程師": {"comment": "新的總評"}})
    score_batch([ok_job], prefs, "新的經歷", lambda: client, _no_progress, **_store(db_conn))
    after_auto = _records(db_conn, "ok")

    assert after_manual[0] == auto
    assert [r["評分來源"] for r in after_manual] == ["auto", "manual"]
    assert after_auto[:2] == after_manual
    assert [r["評分來源"] for r in after_auto] == ["auto", "manual", "auto"]
    assert after_auto[2]["評語"] == "新的總評"


def test_score_batch_history_reuses_any_auto_record(ok_job, prefs, make_batch_client, db_conn):
    client = make_batch_client({})

    # 經歷 A → B → A：第三次和第一次送給 AI 的內容相同，沿用第一次的 AI 評分
    for experience in ("經歷 A", "經歷 B", "經歷 A"):
        [result] = score_batch([ok_job], prefs, experience, lambda: client, _no_progress, **_store(db_conn))

    assert len(client.calls) == 2
    assert result.reused
    assert len(_records(db_conn, "ok")) == 3
