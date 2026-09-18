"""工作評分 CLI（score_job.py）的測試：dry-run、被淘汰職缺、資料庫路徑、錯誤處理與供應商隔離。"""

import ast
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

import score_job
from job_db import open_db, save_run
from job_scoring.llm import get_client
from job_scoring.models import AIAssessment

SRC = Path(__file__).resolve().parents[1] / "src"


def _run(jobs_file, profile_dir, *extra):
    return score_job.main(["--jobs", str(jobs_file), "--profile-dir", str(profile_dir), *extra])


def test_main_dry_run_prints_prompt(jobs_file, profile_dir, forbid_client, capsys):
    code = _run(jobs_file, profile_dir, "--job-no", "ok", "--dry-run")
    out = capsys.readouterr().out

    assert code == 0
    for marker in ["目標標記-AAA", "經歷標記-BBB", "工作標記-CCC", "（無資料）"]:
        assert marker in out
    assert forbid_client == []


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


def test_main_batch_dryrun_needs_job_no(jobs_file, profile_dir, forbid_client, scores_dir, capsys):
    code = _run(jobs_file, profile_dir, "--dry-run")

    assert code == 1
    assert "[-]" in capsys.readouterr().err
    assert not scores_dir.exists()


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
