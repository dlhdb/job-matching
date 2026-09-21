"""工作評分 CLI（score_job.py）的測試：被淘汰職缺、資料庫路徑、錯誤處理、沿用上次的 AI 評分、試跑與供應商隔離。"""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

import job_db
import score_job
from job_db import open_db, save_run
from job_scoring.llm import get_client
from job_scoring.models import AIAssessment
from job_scoring.scorer import compute_total

SRC = Path(__file__).resolve().parents[1] / "src"


def _run(jobs_file, profile_dir, *extra):
    return score_job.main(["--jobs", str(jobs_file), "--profile-dir", str(profile_dir), *extra])


def test_main_eliminated_needs_no_api_key(jobs_file, profile_dir, forbid_client, capsys):
    code = _run(jobs_file, profile_dir, "--job-no", "out")
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    assert data["淘汰"] is True
    assert data["淘汰原因"]
    assert forbid_client == []


def test_main_ok_uses_client_and_prints_json(jobs_file, profile_dir, fake_client, monkeypatch, capsys):
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)

    code = _run(jobs_file, profile_dir, "--job-no", "ok")
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    assert data["職缺代碼"] == "ok"
    assert data["總分"] == 75


def test_main_single_writes_default_db(jobs_file, profile_dir, fake_client, isolate_db, monkeypatch):
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)

    code = _run(jobs_file, profile_dir, "--job-no", "ok")

    assert code == 0
    with closing(open_db(isolate_db)) as conn:
        row = conn.execute('SELECT "總分", "供應商" FROM job_scores WHERE "職缺代碼" = ?', ("ok",)).fetchone()
    assert row == (75, "gemini")


def test_main_db_path(tmp_path, jobs_file, profile_dir, make_job, forbid_client):
    db = tmp_path / "other" / "jobs.db"
    conn = open_db(db)
    save_run(conn, [make_job(**{"職缺代碼": "x1"})], datetime(2026, 9, 1, 10, 0, 0), "匯入")
    # 模擬評分入庫之前建立的資料庫：只有 job-database 的三張表
    conn.execute("DROP TABLE job_scores")
    jobs_before = conn.execute("SELECT * FROM jobs").fetchall()
    conn.close()

    code = _run(jobs_file, profile_dir, "--job-no", "out", "--db", str(db))

    assert code == 0
    conn = open_db(db)
    try:
        rows = conn.execute('SELECT "職缺代碼", "淘汰" FROM job_scores').fetchall()
        assert rows == [("out", 1)]
        assert conn.execute("SELECT * FROM jobs").fetchall() == jobs_before
    finally:
        conn.close()


def test_error_db_unopenable(tmp_path, jobs_file, profile_dir, forbid_client, capsys):
    db_dir = tmp_path / "is_a_directory"
    db_dir.mkdir()

    code = _run(jobs_file, profile_dir, "--job-no", "out", "--db", str(db_dir))

    assert code == 1
    assert "[-]" in capsys.readouterr().err


def test_error_missing_api_key(jobs_file, profile_dir, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    code = _run(jobs_file, profile_dir, "--job-no", "ok")
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err
    assert "GEMINI_API_KEY" in err


def test_error_unknown_job_no(jobs_file, profile_dir, forbid_client, capsys):
    code = _run(jobs_file, profile_dir, "--job-no", "does-not-exist")

    assert code == 1
    assert "[-]" in capsys.readouterr().err


def test_error_jobs_file_item_not_object(tmp_path, profile_dir, forbid_client, capsys):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text('["8s12x"]', encoding="utf-8")

    code = _run(jobs_file, profile_dir, "--job-no", "8s12x")

    assert code == 1
    assert "[-]" in capsys.readouterr().err


def test_error_invalid_ai_response(jobs_file, profile_dir, monkeypatch, capsys):
    """AI 回應不符合 schema 時，印出 [-] 並以 1 結束，不自行修正分數"""
    class BadClient:
        def assess(self, system, user):
            return AIAssessment.model_validate_json('{"career_fit": {"score": 6, "reason": "r"}}')

    monkeypatch.setattr(score_job, "get_client", lambda provider, model: BadClient())

    code = _run(jobs_file, profile_dir, "--job-no", "ok")

    assert code == 1
    assert "[-]" in capsys.readouterr().err


@pytest.fixture
def scores_dir(tmp_path, monkeypatch):
    """
    把整批結果的輸出目錄指到 tmp_path

    :return: Path, 輸出目錄
    """
    path = tmp_path / "scores"
    monkeypatch.setattr(score_job, "SCORES_DIR", path)
    return path


def test_main_batch_writes_files_and_summary(jobs_file, profile_dir, fake_client, scores_dir, monkeypatch, capsys):
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)

    code = _run(jobs_file, profile_dir)
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == ""
    assert "共 2 筆，成功 1、淘汰 1、失敗 0" in captured.err
    for suffix in ("json", "csv"):
        path = scores_dir / f"jobs_scored.{suffix}"
        assert path.is_file()
        assert str(path) in captured.err


def test_main_batch_all_eliminated_no_client(tmp_path, profile_dir, out_job, forbid_client, scores_dir):
    jobs_file = tmp_path / "only_out.json"
    jobs_file.write_text(json.dumps([out_job], ensure_ascii=False), encoding="utf-8")

    code = _run(jobs_file, profile_dir)
    records = json.loads((scores_dir / "only_out_scored.json").read_text(encoding="utf-8"))

    assert code == 0
    assert [r["淘汰"] for r in records] == [True]
    assert forbid_client == []


def test_main_batch_missing_api_key(jobs_file, profile_dir, scores_dir, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    code = _run(jobs_file, profile_dir)
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err
    assert "GEMINI_API_KEY" in err
    assert not scores_dir.exists()


def test_error_unknown_provider():
    with pytest.raises(ValueError):
        get_client("no-such-provider", "any-model")


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_error_provider_sdk_isolated_to_llm():
    files = [*sorted((SRC / "job_scoring").glob("*.py")), SRC / "score_job.py"]
    importing_google = {
        path.name for path in files
        if any(name == "google" or name.startswith("google.") for name in _imported_modules(path))
    }

    assert importing_google == {"llm.py"}


# 單筆評分結果的鍵，用來從整批結果檔取出評分欄位
JOB_SCORE_KEYS = ["職缺代碼", "淘汰", "淘汰原因", "維度", "總分", "未知維度", "評語"]


@pytest.fixture
def counted_client(fake_client, monkeypatch):
    """
    讓 CLI 使用假的 LLM client

    :return: FakeLLMClient, 以 len(client.calls) 取得呼叫次數
    """
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)
    return fake_client


def _stored_result(db, job_no):
    """
    取出資料庫中某筆職缺最新一筆自動評分的總分與評分明細

    :return: tuple (int or None, dict)
    """
    with closing(open_db(db)) as conn:
        total, result = conn.execute(
            'SELECT "總分", "評分明細" FROM job_scores WHERE "職缺代碼" = ? AND "評分來源" = \'auto\' '
            'ORDER BY "評分編號" DESC LIMIT 1', (job_no,)).fetchone()
    return total, json.loads(result)


def _ai_part(result):
    """
    取出評分結果中 AI 產生的部分：三個 AI 維度與評語

    :return: dict
    """
    return {"維度": {name: result["維度"][name] for name in list(result["維度"])[:3]}, "評語": result["評語"]}


def test_main_cache_reuses_on_rerun(jobs_file, profile_dir, counted_client, scores_dir, isolate_db, capsys):
    json_path, csv_path = scores_dir / "jobs_scored.json", scores_dir / "jobs_scored.csv"

    assert _run(jobs_file, profile_dir) == 0
    capsys.readouterr()
    first_files = json_path.read_bytes(), csv_path.read_bytes()
    _, first_stored = _stored_result(isolate_db, "ok")
    assert len(counted_client.calls) == 1

    assert _run(jobs_file, profile_dir) == 0
    err = capsys.readouterr().err
    _, second_stored = _stored_result(isolate_db, "ok")

    assert len(counted_client.calls) == 1
    assert "沿用上次的 AI 評分：1 筆" in err
    assert "成功 1" in err
    assert _ai_part(second_stored) == _ai_part(first_stored)
    assert (json_path.read_bytes(), csv_path.read_bytes()) == first_files


@pytest.mark.parametrize("change", ["experience", "model"])
def test_main_cache_miss_on_ai_input_change(change, jobs_file, profile_dir, counted_client, scores_dir):
    assert _run(jobs_file, profile_dir) == 0
    extra = []
    if change == "experience":
        (profile_dir / "experience.md").write_text("另一份經歷", encoding="utf-8")
    else:
        extra = ["--model", "另一個模型"]

    assert _run(jobs_file, profile_dir, *extra) == 0

    assert len(counted_client.calls) == 2


def test_main_cache_salary_change_rescored(jobs_file, profile_dir, counted_client, scores_dir, isolate_db,
                                           make_job, out_job):
    assert _run(jobs_file, profile_dir) == 0
    old_total, old_result = _stored_result(isolate_db, "ok")
    higher = make_job(**{"薪資待遇": "月薪80,000~90,000元", "薪資下限": 80000, "薪資上限": 90000})
    jobs_file.write_text(json.dumps([higher, out_job], ensure_ascii=False), encoding="utf-8")

    assert _run(jobs_file, profile_dir) == 0
    new_total, new_result = _stored_result(isolate_db, "ok")

    assert len(counted_client.calls) == 1
    assert new_result["維度"]["薪資水準"]["分數"] > old_result["維度"]["薪資水準"]["分數"]
    assert new_total > old_total
    assert new_result["總分"] == new_total


def test_main_cache_weight_change(jobs_file, profile_dir, counted_client, scores_dir, isolate_db,
                                  write_profile, preferences_data):
    assert _run(jobs_file, profile_dir) == 0
    old_total, _ = _stored_result(isolate_db, "ok")
    weights = {"職涯方向契合度": 0.1, "技能匹配度": 0.1, "產業公司吸引力": 0.1, "薪資水準": 0.7}
    write_profile({**preferences_data, "權重": weights})

    assert _run(jobs_file, profile_dir) == 0
    new_total, new_result = _stored_result(isolate_db, "ok")

    assert len(counted_client.calls) == 1
    scores = {name: d["分數"] for name, d in new_result["維度"].items()}
    assert new_total == compute_total(scores, weights)
    assert new_total != old_total


def test_main_cache_no_api_key(jobs_file, profile_dir, counted_client, scores_dir, monkeypatch):
    assert _run(jobs_file, profile_dir) == 0

    def _forbidden(*args, **kwargs):
        pytest.fail("沿用時不應建立 LLM client")

    monkeypatch.setattr(score_job, "get_client", _forbidden)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    assert _run(jobs_file, profile_dir) == 0


def test_main_cache_single_job(jobs_file, profile_dir, counted_client, scores_dir, capsys):
    assert _run(jobs_file, profile_dir) == 0
    record = next(r for r in json.loads((scores_dir / "jobs_scored.json").read_text(encoding="utf-8"))
                  if r["職缺代碼"] == "ok")
    capsys.readouterr()

    code = _run(jobs_file, profile_dir, "--job-no", "ok")
    captured = capsys.readouterr()

    assert code == 0
    assert len(counted_client.calls) == 1
    assert json.loads(captured.out) == {key: record[key] for key in JOB_SCORE_KEYS}
    assert "沿用上次的 AI 評分結果" in captured.err


def _score_rows(db):
    """
    取出 job_scores 的所有列，用來確認試跑沒有改動資料庫

    :return: list[tuple]
    """
    with closing(open_db(db)) as conn:
        return conn.execute('SELECT * FROM job_scores ORDER BY "職缺代碼"').fetchall()


def test_main_dry_run_single(jobs_file, profile_dir, counted_client, scores_dir, isolate_db, capsys):
    assert _run(jobs_file, profile_dir) == 0
    rows_before = _score_rows(isolate_db)
    capsys.readouterr()

    for _ in range(2):
        code = _run(jobs_file, profile_dir, "--job-no", "ok", "--dry-run")
        captured = capsys.readouterr()
        records = json.loads((scores_dir / "jobs_dryrun.json").read_text(encoding="utf-8"))

        assert code == 0
        assert captured.out == ""
        assert [r["職缺代碼"] for r in records] == ["ok"]
        assert records[0]["總分"] == 75

    # 正式評分 1 次，兩次試跑各 1 次，試跑不沿用上次的 AI 評分
    assert len(counted_client.calls) == 3
    system, user = counted_client.calls[-1]
    for marker in ["目標標記-AAA", "經歷標記-BBB", "工作標記-CCC", "（無資料）"]:
        assert marker in system + user
    assert _score_rows(isolate_db) == rows_before


def test_main_dry_run_all_jobs(jobs_file, profile_dir, counted_client, scores_dir, isolate_db, capsys):
    assert _run(jobs_file, profile_dir) == 0
    rows_before = _score_rows(isolate_db)
    scored_files = [(scores_dir / f"jobs_scored.{suffix}").read_bytes() for suffix in ("json", "csv")]
    capsys.readouterr()

    code = _run(jobs_file, profile_dir, "--dry-run")
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == ""
    assert "共 2 筆，成功 1、淘汰 1、失敗 0" in captured.err
    for suffix in ("json", "csv"):
        path = scores_dir / f"jobs_dryrun.{suffix}"
        assert path.is_file()
        assert str(path) in captured.err
    assert len(counted_client.calls) == 2
    assert [(scores_dir / f"jobs_scored.{suffix}").read_bytes() for suffix in ("json", "csv")] == scored_files
    assert _score_rows(isolate_db) == rows_before


def test_main_dry_run_no_db_created(tmp_path, jobs_file, profile_dir, counted_client, scores_dir):
    db = tmp_path / "missing" / "jobs.db"

    code = _run(jobs_file, profile_dir, "--job-no", "ok", "--dry-run", "--db", str(db))

    assert code == 0
    assert not db.exists()
    assert not db.parent.exists()


def test_main_history_no_delete(jobs_file, profile_dir, fake_client, isolate_db, monkeypatch, capsys):
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)
    with pytest.raises(SystemExit):
        score_job.main(["--help"])
    help_text = capsys.readouterr().out.lower()

    # 評分資料庫與評分 CLI 都沒有刪除評分紀錄的操作
    forbidden = ("delete", "remove", "clear", "reset", "purge", "drop", "刪除", "清除", "清掉")
    assert not [name for name in job_db.__all__ if any(word in name.lower() for word in forbidden)]
    assert not [word for word in forbidden if word in help_text]

    # 重跑整批後，原本的評分紀錄都還在
    assert _run(jobs_file, profile_dir) == 0
    with closing(open_db(isolate_db)) as conn:
        before = conn.execute('SELECT * FROM job_scores ORDER BY "評分編號"').fetchall()
    assert _run(jobs_file, profile_dir) == 0
    with closing(open_db(isolate_db)) as conn:
        after = conn.execute('SELECT * FROM job_scores ORDER BY "評分編號"').fetchall()
    assert before and after[:len(before)] == before


def test_main_old_db_error(tmp_path, jobs_file, profile_dir, forbid_client, capsys):
    db = tmp_path / "old.db"
    # 評分紀錄的資料表是舊版：以職缺代碼為主鍵，沒有評分來源
    with closing(sqlite3.connect(db)) as old:
        old.execute(
            'CREATE TABLE job_scores ("職缺代碼" TEXT PRIMARY KEY, "評分時間" TEXT NOT NULL, '
            '"淘汰" INTEGER NOT NULL, "總分" INTEGER, "評語" TEXT, "評分結果" TEXT, '
            '"快取鍵" TEXT, "供應商" TEXT, "模型" TEXT)'
        )

    code = _run(jobs_file, profile_dir, "--job-no", "ok", "--db", str(db))

    assert code == 1
    assert "刪除資料庫檔後重建" in capsys.readouterr().err
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'job_scores_manual'").fetchone() is None
