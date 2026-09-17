"""整批評分（job_scoring.batch）的測試：逐筆評分、單筆失敗不中斷、結果檔。"""

import csv
import json

import pytest

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
def five_results(five_jobs, prefs, make_batch_client):
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
    return score_batch(five_jobs, prefs, "經歷", lambda: client, _no_progress), client


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


def test_score_batch_failure_does_not_stop(make_job, prefs, make_batch_client):
    jobs = [
        make_job(**{"職缺代碼": "a", "職缺名稱": "甲職缺"}),
        make_job(**{"職缺代碼": "b", "職缺名稱": "乙職缺"}),
        make_job(**{"職缺代碼": "c", "職缺名稱": "丙職缺"}),
    ]
    client = make_batch_client({"甲職缺": "llm_error", "乙職缺": "invalid", "丙職缺": {}})

    results = score_batch(jobs, prefs, "經歷", lambda: client, _no_progress)

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


def test_score_batch_client_created_lazily(out_job, prefs):
    def _factory():
        pytest.fail("全部被淘汰時不應建立 client")

    progress = []
    results = score_batch([out_job, out_job], prefs, "經歷", _factory, progress.append)

    assert all(r.eliminated for r in results)
    assert progress[1].startswith("⏳ [i] (2/2) 業務專員 - 甲公司")


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
