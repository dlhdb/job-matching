"""匯入 CLI 的離線測試。JSON 與資料庫都建在 tmp_path。"""

import json
from datetime import datetime

import pytest

import import_jobs
from job_db import open_db

TABLES = ("jobs", "scrape_runs", "run_jobs")


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def dump_db(db_path):
    """
    取出三個表的全部內容

    :return: dict[str, list[tuple]]
    """
    conn = open_db(db_path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in TABLES}
    finally:
        conn.close()


@pytest.fixture
def files(tmp_path, make_job):
    """
    兩個合法檔（部分重疊）、一個檔名沒有時間的檔，以及一個內容不是職缺清單的檔

    :return: dict[str, Path]
    """
    src = tmp_path / "src"
    src.mkdir()
    return {
        "old": write_json(src / "jobs_104_A_20260901_100000.json",
                          [make_job(職缺代碼="a"), make_job(職缺代碼="b", 職缺名稱="舊名稱")]),
        "new": write_json(src / "jobs_104_B_20260917_101500.json",
                          [make_job(職缺代碼="b", 職缺名稱="新名稱"), make_job(職缺代碼="c")]),
        "no_time": write_json(src / "jobs.json", [make_job()]),
        "bad": write_json(src / "jobs_104_C_20260910_080000.json", {"不是": "清單"}),
    }


@pytest.mark.parametrize("name, expected", [
    ("jobs_104_Python_20260917_101500.json", datetime(2026, 9, 17, 10, 15, 0)),
    ("output/104/jobs_104_all_20260101_000000.json", datetime(2026, 1, 1, 0, 0, 0)),
    ("jobs.json", None),
    ("jobs_104_Python_20260917_101500.csv", None),
    ("jobs_104_Python_20261399_101500.json", None),  # 格式相符但日期不合法
])
def test_parse_run_time(name, expected):
    assert import_jobs.parse_run_time(name) == expected


def test_import_jobs_main_imports_and_skips(tmp_path, files, capsys):
    db = tmp_path / "db" / "jobs.db"
    # 新檔排在舊檔前面，驗證匯入順序不影響結果
    argv = [str(files[k]) for k in ("new", "no_time", "bad", "old")] + ["--db", str(db)]

    assert import_jobs.main(argv) == 0

    err = capsys.readouterr().err
    assert err.count("[+] 已寫入資料庫") == 2
    assert "[!] 略過 jobs.json" in err
    assert "[!] 略過 jobs_104_C_20260910_080000.json" in err
    assert "[i]" not in err

    tables = dump_db(db)
    jobs = {row[0]: row for row in tables["jobs"]}
    assert sorted(jobs) == ["a", "b", "c"]
    assert jobs["a"][-2:] == ("2026-09-01T10:00:00", "2026-09-01T10:00:00")
    assert jobs["b"][-2:] == ("2026-09-01T10:00:00", "2026-09-17T10:15:00")
    assert jobs["b"][1] == "新名稱"
    assert jobs["c"][-2:] == ("2026-09-17T10:15:00", "2026-09-17T10:15:00")
    runs = tables["scrape_runs"]
    assert [(r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in runs] == [
        ("2026-09-17T10:15:00", "匯入", None, None, None, None, "jobs_104_B_20260917_101500.json", 2),
        ("2026-09-01T10:00:00", "匯入", None, None, None, None, "jobs_104_A_20260901_100000.json", 2),
    ]

    # 再匯入一次：合法檔案都已匯入過，錯誤檔案仍然略過，資料庫不變
    assert import_jobs.main(argv) == 0

    err = capsys.readouterr().err
    assert "[+]" not in err
    assert "[i] 已匯入過，略過 jobs_104_B_20260917_101500.json" in err
    assert "[i] 已匯入過，略過 jobs_104_A_20260901_100000.json" in err
    assert err.count("[!]") == 2
    assert dump_db(db) == tables


@pytest.mark.parametrize("content", [
    "不是 JSON",
    "[]",
    '[{"職缺名稱": "沒有代碼"}]',
    '["不是物件"]',
])
def test_import_jobs_main_invalid_files_return_1(tmp_path, capsys, content):
    path = tmp_path / "jobs_104_A_20260901_100000.json"
    path.write_text(content, encoding="utf-8")
    db = tmp_path / "jobs.db"

    assert import_jobs.main([str(path), "--db", str(db)]) == 1

    assert "[!]" in capsys.readouterr().err
    assert dump_db(db) == {t: [] for t in TABLES}


def test_import_jobs_main_missing_file_returns_1(tmp_path, capsys):
    missing = tmp_path / "jobs_104_A_20260901_100000.json"

    assert import_jobs.main([str(missing), "--db", str(tmp_path / "jobs.db")]) == 1
    assert "[!]" in capsys.readouterr().err


def test_import_jobs_main_without_files_returns_1(tmp_path, capsys):
    db = tmp_path / "jobs.db"

    assert import_jobs.main(["--db", str(db)]) == 1

    assert "[-]" in capsys.readouterr().err
    assert not db.exists()
