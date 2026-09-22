"""工作評分 CLI（score_job.py）的測試：選職缺、被淘汰職缺、資料庫路徑、錯誤處理、試跑、評分歷史與供應商隔離。"""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

import job_db
import score_job
from job_db import get_score_details, list_scores, open_db, save_auto_score, save_run, save_score
from job_scoring.llm import get_client

SRC = Path(__file__).resolve().parents[1] / "src"


def _run(db, profile_dir, *extra):
    return score_job.main(["--db", str(db), "--profile-dir", str(profile_dir), *extra])


def _score_rows(db):
    """
    取出 job_scores 的所有列，依評分編號排序

    :return: list[tuple]
    """
    with closing(open_db(db)) as conn:
        return conn.execute('SELECT * FROM job_scores ORDER BY "評分編號"').fetchall()


def _details(db, job_no):
    """
    取出一筆職缺代表的評分的評分明細

    :return: dict or None
    """
    with closing(open_db(db)) as conn:
        return get_score_details(conn, job_no)


def _auto_count(db, job_no):
    """
    一筆職缺的自動評分紀錄筆數

    :return: int
    """
    with closing(open_db(db)) as conn:
        return sum(r["評分來源"] == "auto" for r in list_scores(conn, job_no))


@pytest.fixture
def counted_client(fake_client, monkeypatch):
    """
    讓 CLI 使用假的 LLM client

    :return: FakeLLMClient, 以 len(client.calls) 取得呼叫次數
    """
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: fake_client)
    return fake_client


@pytest.fixture
def scores_dir(tmp_path, monkeypatch):
    """
    把試跑結果檔的輸出目錄指到 tmp_path

    :return: Path, 輸出目錄
    """
    path = tmp_path / "scores"
    monkeypatch.setattr(score_job, "SCORES_DIR", path)
    return path


def _progress_order(err, names):
    """
    依進度訊息出現的先後，排出職缺名稱

    :param err: str, stderr 的內容
    :param names: list[str], 要找的職缺名稱
    :return: list[str], 出現過的名稱，依第一次出現的位置排序
    """
    found = [name for name in names if f") {name} - " in err]
    return sorted(found, key=lambda name: err.index(f") {name} - "))


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------

def test_main_eliminated_needs_no_api_key(tmp_path, profile_dir, out_job, forbid_client, capsys):
    db = tmp_path / "only_out.db"
    with closing(open_db(db)) as conn:
        save_run(conn, [out_job], datetime(2026, 9, 1, 10, 0, 0), "匯入")

    code = _run(db, profile_dir)
    details = _details(db, "out")

    assert code == 0
    assert capsys.readouterr().out == ""
    assert details["淘汰"] is True
    assert details["淘汰原因"]
    assert forbid_client == []


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------

def test_main_unscored_selects_jobs_without_any_score(tmp_path, profile_dir, make_job, counted_client, capsys):
    db = tmp_path / "unscored.db"
    names = ["沒評過-舊", "只有手動", "已有自動", "沒評過-新"]
    with closing(open_db(db)) as conn:
        for day, (job_no, name) in enumerate(zip(["old", "manual", "auto", "new"], names), start=1):
            save_run(conn, [make_job(職缺代碼=job_no, 職缺名稱=name)], datetime(2026, 9, day, 10, 0, 0), "匯入")
        save_score(conn, job_no="manual", comment="手動評語", total=90)
        save_auto_score(conn, job_no="auto", scored_at=datetime(2026, 9, 5), eliminated=False, total=70,
                        comment="舊評語", details={"職缺代碼": "auto"}, provider="gemini", model="舊模型")

    code = _run(db, profile_dir)
    err = capsys.readouterr().err

    assert code == 0
    # 最後出現時間由新到舊，只有手動評分與已有自動評分的職缺都不評
    assert _progress_order(err, names) == ["沒評過-新", "沒評過-舊"]
    assert len(counted_client.calls) == 2
    assert (_auto_count(db, "manual"), _auto_count(db, "auto")) == (0, 1)

    code = _run(db, profile_dir)
    err = capsys.readouterr().err

    assert code == 0
    assert "[i] 沒有還沒評分的職缺" in err
    assert len(counted_client.calls) == 2


def test_main_job_nos(tmp_path, profile_dir, make_job, counted_client, capsys):
    db = tmp_path / "job_nos.db"
    with closing(open_db(db)) as conn:
        save_run(conn, [make_job(職缺代碼=c, 職缺名稱=f"職缺{c}") for c in ("a", "b", "c")],
                 datetime(2026, 9, 1, 10, 0, 0), "匯入")
        save_auto_score(conn, job_no="c", scored_at=datetime(2026, 9, 2), eliminated=False, total=70,
                        comment="舊評語", details={"職缺代碼": "c"}, provider="gemini", model="舊模型")

    # (a) 依指定的順序評，重複的只評一次，已評過的照樣重評
    code = _run(db, profile_dir, "--job-no", "c", "a", "c")
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == ""
    assert _progress_order(captured.err, ["職缺a", "職缺c"]) == ["職缺c", "職缺a"]
    assert "共 2 筆" in captured.err
    assert len(counted_client.calls) == 2

    # (b) 有不存在的職缺代碼時一筆都不評
    rows_before = _score_rows(db)
    code = _run(db, profile_dir, "--job-no", "b", "zzz")
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err and "zzz" in err
    assert _score_rows(db) == rows_before

    # (c) 只指定一筆已評過的職缺，同樣呼叫 AI 重評並印出摘要
    code = _run(db, profile_dir, "--job-no", "c")
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == ""
    assert "共 1 筆" in captured.err
    assert len(counted_client.calls) == 3
    assert _auto_count(db, "c") == 3


def test_main_rescore_failure_keeps_old_score(jobs_db, profile_dir, make_batch_client, monkeypatch, capsys):
    with closing(open_db(jobs_db)) as conn:
        save_auto_score(conn, job_no="ok", scored_at=datetime(2026, 9, 2), eliminated=False, total=70,
                        comment="舊評語", details={"職缺代碼": "ok"}, provider="gemini", model="舊模型")
    rows_before = _score_rows(jobs_db)
    client = make_batch_client({"Python 工程師": "llm_error"})
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: client)

    code = _run(jobs_db, profile_dir, "--job-no", "ok")
    err = capsys.readouterr().err

    assert code == 0
    assert "[!] ok Python 工程師：模擬的 API 錯誤" in err
    assert _score_rows(jobs_db) == rows_before


def test_main_batch_summary_no_files(jobs_db, profile_dir, counted_client, scores_dir, capsys):
    code = _run(jobs_db, profile_dir)
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == ""
    assert "共 2 筆，成功 1、淘汰 1、失敗 0" in captured.err
    assert not scores_dir.exists()


def test_main_batch_all_eliminated_no_client(tmp_path, profile_dir, out_job, forbid_client):
    db = tmp_path / "only_out.db"
    with closing(open_db(db)) as conn:
        save_run(conn, [out_job], datetime(2026, 9, 1, 10, 0, 0), "匯入")

    code = _run(db, profile_dir)

    assert code == 0
    assert _details(db, "out")["淘汰"] is True
    assert forbid_client == []


def test_main_batch_missing_api_key(jobs_db, profile_dir, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    code = _run(jobs_db, profile_dir)
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err
    assert "GEMINI_API_KEY" in err
    # 開始評分前就結束，會被淘汰的那筆也沒有寫入
    assert _score_rows(jobs_db) == []


def test_main_batch_failure_listed(jobs_db, profile_dir, make_batch_client, monkeypatch, capsys):
    client = make_batch_client({"Python 工程師": "llm_error"})
    monkeypatch.setattr(score_job, "get_client", lambda provider, model: client)

    code = _run(jobs_db, profile_dir)
    err = capsys.readouterr().err

    assert code == 0
    assert "失敗 1" in err
    assert "[!] ok Python 工程師：模擬的 API 錯誤" in err


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

def test_main_db_path(tmp_path, profile_dir, out_job, forbid_client):
    db = tmp_path / "other" / "jobs.db"
    conn = open_db(db)
    save_run(conn, [out_job], datetime(2026, 9, 1, 10, 0, 0), "匯入")
    # 模擬評分入庫之前建立的資料庫：只有 job-database 的三張表
    conn.execute("DROP TABLE job_scores")
    jobs_before = conn.execute("SELECT * FROM jobs").fetchall()
    conn.close()

    code = _run(db, profile_dir)

    assert code == 0
    with closing(open_db(db)) as conn:
        assert conn.execute('SELECT "職缺代碼", "淘汰" FROM job_scores').fetchall() == [("out", 1)]
        assert conn.execute("SELECT * FROM jobs").fetchall() == jobs_before


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------

@pytest.fixture
def ticking_now(monkeypatch):
    """
    讓 CLI 每次取得的開始時間各差一秒，從 2026-01-02 03:04:05 開始

    :return: None
    """
    times = iter(datetime(2026, 1, 2, 3, 4, s) for s in range(5, 60))

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(times)

    monkeypatch.setattr(score_job, "datetime", _Clock)


def test_main_dry_run(jobs_db, profile_dir, counted_client, scores_dir, ticking_now, capsys):
    assert _run(jobs_db, profile_dir, "--job-no", "ok") == 0
    rows_before = _score_rows(jobs_db)
    capsys.readouterr()

    # (a) 評同一筆兩次，開始時間不同
    paths = []
    for _ in range(2):
        code = _run(jobs_db, profile_dir, "--job-no", "ok", "--dry-run")
        captured = capsys.readouterr()

        assert code == 0
        assert captured.out == ""
        [path] = sorted(set(scores_dir.glob("dryrun_*.json")) - set(paths))
        paths.append(path)
        assert str(path) in captured.err
        records = json.loads(path.read_text(encoding="utf-8"))
        assert [r["職缺代碼"] for r in records] == ["ok"]
        assert records[0]["總分"] == 75
    first_content = paths[0].read_bytes()

    assert [p.name for p in paths] == ["dryrun_20260102_030406.json", "dryrun_20260102_030407.json"]
    assert paths[0].read_bytes() == first_content
    # 正式評分 1 次，兩次試跑各 1 次
    assert len(counted_client.calls) == 3
    system, user = counted_client.calls[-1]
    for marker in ["目標標記-AAA", "經歷標記-BBB", "工作標記-CCC", "（無資料）"]:
        assert marker in system + user
    assert _score_rows(jobs_db) == rows_before

    # (b) 指定兩筆職缺
    code = _run(jobs_db, profile_dir, "--job-no", "ok", "out", "--dry-run")
    captured = capsys.readouterr()
    [path] = sorted(set(scores_dir.glob("dryrun_*.json")) - set(paths))

    assert code == 0
    assert "[i] 試跑：不寫入資料庫，不影響已存的評分" in captured.err
    assert [r["職缺代碼"] for r in json.loads(path.read_text(encoding="utf-8"))] == ["ok", "out"]
    assert _score_rows(jobs_db) == rows_before


def test_main_dry_run_missing_db(tmp_path, profile_dir, counted_client, scores_dir, capsys):
    db = tmp_path / "missing" / "jobs.db"

    code = _run(db, profile_dir, "--job-no", "ok", "--dry-run")

    assert code == 1
    assert "[-]" in capsys.readouterr().err
    assert not db.parent.exists()
    assert counted_client.calls == []


def test_main_dry_run_requires_job_no(jobs_db, profile_dir, counted_client, scores_dir, capsys):
    code = _run(jobs_db, profile_dir, "--dry-run")

    assert code == 1
    assert "--job-no" in capsys.readouterr().err
    assert counted_client.calls == []
    assert not scores_dir.exists()


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

def test_main_history_no_delete(jobs_db, profile_dir, counted_client, capsys):
    with pytest.raises(SystemExit):
        score_job.main(["--help"])
    help_text = capsys.readouterr().out.lower()

    # 評分資料庫與評分 CLI 都沒有刪除評分紀錄的操作
    forbidden = ("delete", "remove", "clear", "reset", "purge", "drop", "刪除", "清除", "清掉")
    assert not [name for name in job_db.__all__ if any(word in name.lower() for word in forbidden)]
    assert not [word for word in forbidden if word in help_text]

    # 以 --job-no 重評後，原本的評分紀錄都還在
    assert _run(jobs_db, profile_dir) == 0
    before = _score_rows(jobs_db)
    assert _run(jobs_db, profile_dir, "--job-no", "ok", "out") == 0
    after = _score_rows(jobs_db)
    assert before and after[:len(before)] == before
    assert len(after) == len(before) * 2


# ---------------------------------------------------------------------------
# 共用規則：錯誤處理
# ---------------------------------------------------------------------------

def test_error_missing_api_key(jobs_db, profile_dir, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    code = _run(jobs_db, profile_dir, "--job-no", "ok")
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err
    assert "GEMINI_API_KEY" in err


def test_error_unknown_job_no(jobs_db, profile_dir, forbid_client, capsys):
    code = _run(jobs_db, profile_dir, "--job-no", "does-not-exist")
    err = capsys.readouterr().err

    assert code == 1
    assert "[-]" in err and "does-not-exist" in err


def test_error_unknown_provider(jobs_db, profile_dir, capsys):
    with pytest.raises(ValueError):
        get_client("no-such-provider", "any-model")

    code = _run(jobs_db, profile_dir, "--job-no", "ok", "--provider", "no-such-provider")

    assert code == 1
    assert "no-such-provider" in capsys.readouterr().err


def test_error_db_missing(tmp_path, profile_dir, forbid_client, capsys):
    db = tmp_path / "missing" / "jobs.db"

    code = _run(db, profile_dir, "--job-no", "out")

    assert code == 1
    assert "[-]" in capsys.readouterr().err
    assert not db.parent.exists()


def test_error_db_unopenable(tmp_path, profile_dir, forbid_client, capsys):
    db_dir = tmp_path / "is_a_directory"
    db_dir.mkdir()

    code = _run(db_dir, profile_dir, "--job-no", "out")

    assert code == 1
    assert "[-]" in capsys.readouterr().err


def test_main_old_db_error(tmp_path, profile_dir, forbid_client, capsys):
    db = tmp_path / "old.db"
    # 評分紀錄的資料表是舊版：以職缺代碼為主鍵，沒有評分來源
    with closing(sqlite3.connect(db)) as old:
        old.execute(
            'CREATE TABLE job_scores ("職缺代碼" TEXT PRIMARY KEY, "評分時間" TEXT NOT NULL, '
            '"淘汰" INTEGER NOT NULL, "總分" INTEGER, "評語" TEXT, "評分結果" TEXT, '
            '"快取鍵" TEXT, "供應商" TEXT, "模型" TEXT)'
        )

    code = _run(db, profile_dir, "--job-no", "ok")

    assert code == 1
    assert "刪除資料庫檔後重建" in capsys.readouterr().err


def test_open_db_migrates_cache_column_and_manual_index(tmp_path):
    db = tmp_path / "cache.db"
    # 拿掉快取之前的資料表：有快取鍵，且每筆職缺最多一筆手動評分
    with closing(sqlite3.connect(db)) as old:
        old.execute(
            'CREATE TABLE job_scores ("評分編號" INTEGER PRIMARY KEY AUTOINCREMENT, "職缺代碼" TEXT NOT NULL, '
            '"評分來源" TEXT NOT NULL, "評分時間" TEXT NOT NULL, "淘汰" INTEGER NOT NULL, "總分" INTEGER, '
            '"評語" TEXT, "評分明細" TEXT, "快取鍵" TEXT, "供應商" TEXT, "模型" TEXT)'
        )
        old.execute('CREATE UNIQUE INDEX job_scores_manual ON job_scores("職缺代碼") WHERE "評分來源" = \'manual\'')
        old.execute(
            'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", "淘汰", "總分", "評語", "評分明細", "快取鍵") '
            "VALUES ('a', 'auto', '2026-09-01T10:00:00', 0, 70, '舊評語', '{}', '舊鍵')"
        )
        old.commit()

    with closing(open_db(db)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(job_scores)")}
        index = conn.execute("SELECT name FROM sqlite_master WHERE name = 'job_scores_manual'").fetchone()
        save_score(conn, job_no="a", comment="第一次")
        save_score(conn, job_no="a", comment="第二次")
        sources = [r["評分來源"] for r in list_scores(conn, "a")]

    assert "快取鍵" not in columns
    assert index is None
    assert sorted(sources) == ["auto", "manual", "manual"]


# ---------------------------------------------------------------------------
# 供應商隔離
# ---------------------------------------------------------------------------

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
