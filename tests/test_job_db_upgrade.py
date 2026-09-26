"""資料庫改版的測試：各種舊版的 job_scores 改成最新版、保留職缺與執行紀錄、略過無法表示的評分、失敗時還原。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

import job_db.upgrade
from job_db import LATEST_VERSION, open_db, save_auto_score, upgrade_db
from job_db.schema import JOB_DDL
from job_db.upgrade import UpgradeError

# 最舊版：每筆職缺一列，評分明細叫評分結果；手動評分沒有評分結果
OLDEST = """
    CREATE TABLE job_scores (
        "職缺代碼" TEXT PRIMARY KEY, "評分時間" TEXT NOT NULL, "淘汰" INTEGER NOT NULL, "總分" INTEGER,
        "評語" TEXT, "評分結果" TEXT, "快取鍵" TEXT, "供應商" TEXT, "模型" TEXT
    )
"""

# 有評分來源、還留著快取鍵與限制手動評分的唯一索引
WITH_CACHE = [
    """
    CREATE TABLE job_scores (
        "評分編號" INTEGER PRIMARY KEY AUTOINCREMENT, "職缺代碼" TEXT NOT NULL,
        "評分來源" TEXT NOT NULL CHECK ("評分來源" IN ('auto', 'manual')), "評分時間" TEXT NOT NULL,
        "淘汰" INTEGER NOT NULL, "總分" INTEGER, "評語" TEXT, "評分明細" TEXT, "快取鍵" TEXT, "供應商" TEXT, "模型" TEXT
    )
    """,
    'CREATE UNIQUE INDEX job_scores_manual ON job_scores("職缺代碼") WHERE "評分來源" = \'manual\'',
    'CREATE INDEX job_scores_job ON job_scores("職缺代碼", "評分時間")',
]

# 拿掉快取之後、開始記版本之前的版本
WITH_SOURCE = [
    """
    CREATE TABLE job_scores (
        "評分編號" INTEGER PRIMARY KEY AUTOINCREMENT, "職缺代碼" TEXT NOT NULL,
        "評分來源" TEXT NOT NULL CHECK ("評分來源" IN ('auto', 'manual')), "評分時間" TEXT NOT NULL,
        "淘汰" INTEGER NOT NULL, "總分" INTEGER, "評語" TEXT, "評分明細" TEXT, "供應商" TEXT, "模型" TEXT
    )
    """,
    'CREATE INDEX job_scores_job ON job_scores("職缺代碼", "評分時間")',
]

SCORE_FIELDS = ["職缺代碼", "評分時間", "淘汰", "總分", "評語", "評分明細", "供應商", "模型"]


def _details(job_no, total):
    return json.dumps({"職缺代碼": job_no, "總分": total}, ensure_ascii=False)


def _seed_jobs(conn, make_job):
    """舊版資料庫共有的職缺、執行紀錄與每次寫入出現的職缺：A、B 兩筆職缺，兩次執行"""
    for ddl in JOB_DDL:
        conn.execute(ddl)
    seen = {"A": ("2026-09-01T10:00:00", "2026-09-02T10:00:00"), "B": ("2026-09-02T10:00:00", "2026-09-02T10:00:00")}
    for code, times in seen.items():
        job = make_job(職缺代碼=code, 工作內容=f"{code} 的工作內容")
        columns = ", ".join(f'"{name}"' for name in [*job, "首次出現時間", "最後出現時間"])
        conn.execute(f"INSERT INTO jobs ({columns}) VALUES ({', '.join('?' * (len(job) + 2))})", [*job.values(), *times])
    conn.execute(
        'INSERT INTO scrape_runs ("執行時間", "來源", "關鍵字", "地區", "職缺性質", "頁數", "來源檔", "職缺數") '
        "VALUES ('2026-09-01T10:00:00', '匯入', 'Python', '台北市', 0, 3, 'a.json', 1), "
        "('2026-09-02T10:00:00', '爬蟲', 'Go', NULL, 1, 1, NULL, 2)"
    )
    conn.execute('INSERT INTO run_jobs VALUES (1, \'A\'), (2, \'A\'), (2, \'B\')')


def _build_oldest(conn, make_job):
    _seed_jobs(conn, make_job)
    conn.execute(OLDEST)
    conn.executemany(
        "INSERT INTO job_scores VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
        [
            ("B", "2026-09-03T09:00:00", 1, None, None, _details("B", None), None, None),  # 淘汰、評語是 NULL 的最舊資料
            ("A", "2026-09-03T09:00:00", 0, 70, "A 的評語", _details("A", 70), "gemini", "舊模型"),
            ("M", "2026-09-03T09:00:00", 0, 90, "手動的評語", None, None, None),  # 手動評分
            ("X", "2026-09-03T09:00:00", 0, 50, "X 的評語", _details("X", 50), "gemini", "舊模型"),  # 沒有對應職缺
        ],
    )


def _build_with_source(conn, make_job, ddl):
    _seed_jobs(conn, make_job)
    for statement in ddl:
        conn.execute(statement)
    rows = [
        ("A", "auto", "2026-09-03T09:00:00", 0, 60, "A 較早的評語", _details("A", 60), "gemini", "舊模型"),
        ("A", "manual", "2026-09-03T09:00:00", 0, 90, "手動的評語", None, None, None),
        ("X", "auto", "2026-09-03T09:00:00", 0, 50, "X 的評語", _details("X", 50), "gemini", "舊模型"),
        ("A", "auto", "2026-09-03T09:00:00", 0, 70, "A 同一秒後寫入的評語", _details("A", 70), "gemini", "舊模型"),
        ("B", "auto", "2026-09-04T09:00:00", 1, None, "淘汰：職稱含排除關鍵字：業務", _details("B", None), None, None),
    ]
    columns = '"職缺代碼", "評分來源", "評分時間", "淘汰", "總分", "評語", "評分明細", "供應商", "模型"'
    conn.executemany(f"INSERT INTO job_scores ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


# 每種舊版改版後應該留下的評分：依評分編號排列，以及略過的手動、沒有對應職缺的筆數
LEGACY = {
    "最舊版": (
        _build_oldest,
        [
            (1, "B", "2026-09-03T09:00:00", 1, None, None, _details("B", None), None, None),
            (2, "A", "2026-09-03T09:00:00", 0, 70, "A 的評語", _details("A", 70), "gemini", "舊模型"),
        ],
        1, 1,
    ),
    "有評分來源與快取鍵": (
        lambda conn, make_job: _build_with_source(conn, make_job, WITH_CACHE),
        [
            (1, "A", "2026-09-03T09:00:00", 0, 60, "A 較早的評語", _details("A", 60), "gemini", "舊模型"),
            (4, "A", "2026-09-03T09:00:00", 0, 70, "A 同一秒後寫入的評語", _details("A", 70), "gemini", "舊模型"),
            (5, "B", "2026-09-04T09:00:00", 1, None, "淘汰：職稱含排除關鍵字：業務", _details("B", None), None, None),
        ],
        1, 1,
    ),
    "有評分來源": (
        lambda conn, make_job: _build_with_source(conn, make_job, WITH_SOURCE),
        [
            (1, "A", "2026-09-03T09:00:00", 0, 60, "A 較早的評語", _details("A", 60), "gemini", "舊模型"),
            (4, "A", "2026-09-03T09:00:00", 0, 70, "A 同一秒後寫入的評語", _details("A", 70), "gemini", "舊模型"),
            (5, "B", "2026-09-04T09:00:00", 1, None, "淘汰：職稱含排除關鍵字：業務", _details("B", None), None, None),
        ],
        1, 1,
    ),
}


def _legacy_db(path, build, make_job):
    with closing(sqlite3.connect(path)) as conn, conn:
        build(conn, make_job)
    return path


def _rows(path, table, order):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()


def _job_tables(path):
    """職缺資料庫負責保存的三張表的全部內容"""
    return {
        "jobs": _rows(path, "jobs", '"職缺代碼"'),
        "scrape_runs": _rows(path, "scrape_runs", '"執行編號"'),
        "run_jobs": _rows(path, "run_jobs", '"執行編號", "職缺代碼"'),
    }


def _dump(path):
    with closing(sqlite3.connect(path)) as conn:
        return list(conn.iterdump()), conn.execute("PRAGMA user_version").fetchone()[0]


@pytest.mark.parametrize("name", list(LEGACY))
def test_upgrade_keeps_data(name, tmp_path, make_job):
    build, expected_scores, skipped_manual, skipped_orphan = LEGACY[name]
    path = _legacy_db(tmp_path / "jobs.db", build, make_job)
    before = _job_tables(path)
    before_dump = _dump(path)

    result = upgrade_db(path)

    # 職缺、執行紀錄與每次寫入出現的職缺都和改版前相同（job-database 的 AC-nfr-migration (a)）
    assert _job_tables(path) == before
    # 評分紀錄的筆數與內容相同，手動與沒有對應職缺的略過並計數（job-auto-scoring 的 AC-nfr-migration (a)）
    columns = ", ".join(f'"{c}"' for c in ["評分編號", *SCORE_FIELDS])
    assert _rows(path, f"(SELECT {columns} FROM job_scores)", '"評分編號"') == expected_scores
    basis = _rows(path, '(SELECT "偏好版本", "經歷版本", "模板版本", "職缺快照" FROM job_scores)', "1")
    assert all(row == (None, None, None, None) for row in basis)
    assert (result.from_version, result.to_version) == (0, LATEST_VERSION)
    assert (result.scores_moved, result.skipped_manual, result.skipped_orphan) == (
        len(expected_scores), skipped_manual, skipped_orphan,
    )
    # 備份是改版前的內容，改版成功後留著
    assert result.backup.parent == tmp_path
    assert result.backup.name.startswith("jobs.db.v0-") and result.backup.suffix == ".bak"
    assert _dump(result.backup) == before_dump
    # 改版後 open_db 可以正常開啟，設定的資料表是空的
    with closing(open_db(path)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
        assert conn.execute("SELECT COUNT(*) FROM settings_versions").fetchone()[0] == 0
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "job_scores_job" in indexes and "job_scores_manual" not in indexes


def test_upgrade_without_job_scores(tmp_path, make_job):
    path = _legacy_db(tmp_path / "jobs.db", _seed_jobs, make_job)

    result = upgrade_db(path)

    assert (result.scores_moved, result.skipped_manual, result.skipped_orphan) == (0, 0, 0)
    with closing(open_db(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0] == 0


def test_upgrade_failure_restores(tmp_path, make_job, monkeypatch):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)
    before = _dump(path)
    original = job_db.upgrade._v0_to_v1

    def _fail_midway(conn):
        # 新表已經建好、評分已經搬過去之後才失敗
        original(conn)
        raise RuntimeError("模擬的改版失敗")

    monkeypatch.setattr(job_db.upgrade, "_v0_to_v1", _fail_midway)

    with pytest.raises(UpgradeError, match="模擬的改版失敗") as info:
        upgrade_db(path)

    # 兩個功能的 AC-nfr-migration (b)：顯示錯誤，資料庫還原成改版前的內容
    assert _dump(path) == before
    assert "改版前的備份" in str(info.value)
    with pytest.raises(sqlite3.DatabaseError, match="舊版"):
        open_db(path)


def test_upgrade_concurrent_start_upgrades_once(tmp_path, make_job, monkeypatch):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)
    original = job_db.upgrade._backup_path
    first = []

    def _other_process_first(path, version):
        # 這個程式讀完版本、還沒拿到寫入鎖之前，另一個同時啟動的程式先改好了
        monkeypatch.setattr(job_db.upgrade, "_backup_path", original)
        first.append(upgrade_db(path))
        return original(path, version)

    monkeypatch.setattr(job_db.upgrade, "_backup_path", _other_process_first)

    assert upgrade_db(path) is None

    # 只改了一次：評分明細與評分編號都是第一次改版的結果，也只留下那一次的備份
    columns = ", ".join(f'"{c}"' for c in ["評分編號", *SCORE_FIELDS])
    assert _rows(path, f"(SELECT {columns} FROM job_scores)", '"評分編號"') == LEGACY["有評分來源"][1]
    assert sorted(tmp_path.glob("*.bak")) == [first[0].backup]


def test_upgrade_unknown_job_scores_layout(tmp_path, make_job):
    def _build(conn, make_job):
        _seed_jobs(conn, make_job)
        conn.execute('CREATE TABLE job_scores ("職缺代碼" TEXT, "分數" INTEGER)')

    path = _legacy_db(tmp_path / "jobs.db", _build, make_job)
    before = _dump(path)

    with pytest.raises(UpgradeError, match="看不出 job_scores 是哪一種舊版，欄位：分數、職缺代碼"):
        upgrade_db(path)

    assert _dump(path) == before


def test_upgrade_locked_db_changes_nothing(tmp_path, make_job):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)
    before = _dump(path)

    # 其他程式正在寫入，鎖住了資料庫
    with closing(sqlite3.connect(path, timeout=0)) as other:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(UpgradeError, match="無法開始改版，資料庫沒有改動"):
            upgrade_db(path)
        other.rollback()

    assert _dump(path) == before


def test_upgrade_restore_failure_still_upgrade_error(tmp_path, make_job, monkeypatch):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)

    def _fail(conn):
        # 把備份檔換成壞掉的內容，讓還原也失敗
        for backup in tmp_path.glob("*.bak"):
            backup.write_text("不是資料庫")
        raise RuntimeError("模擬的改版失敗")

    monkeypatch.setattr(job_db.upgrade, "_v0_to_v1", _fail)

    with pytest.raises(UpgradeError, match="模擬的改版失敗（自動還原也失敗"):
        upgrade_db(path)


def test_upgrade_foreign_key_violation_restores(tmp_path, make_job):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("INSERT INTO run_jobs VALUES (2, 'Z')")
    before = _dump(path)

    with pytest.raises(UpgradeError, match="違反外鍵（run_jobs）"):
        upgrade_db(path)

    assert _dump(path) == before


def test_upgrade_backup_failure_changes_nothing(tmp_path, make_job, monkeypatch):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)
    before = _dump(path)

    def _unwritable(path, version):
        return tmp_path / "沒有這個目錄" / "jobs.db.bak"

    monkeypatch.setattr(job_db.upgrade, "_backup_path", _unwritable)

    with pytest.raises(UpgradeError, match="無法備份，沒有改版"):
        upgrade_db(path)

    assert _dump(path) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.db"]


def test_upgrade_backup_name_does_not_overwrite(tmp_path, make_job, monkeypatch):
    path = _legacy_db(tmp_path / "jobs.db", LEGACY["有評分來源"][0], make_job)

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 26, 10, 0, 0)

    monkeypatch.setattr(job_db.upgrade, "datetime", _Fixed)
    (tmp_path / "jobs.db.v0-20260926_100000.bak").write_text("別的檔案")

    result = upgrade_db(path)

    assert result.backup == tmp_path / "jobs.db.v0-20260926_100000_2.bak"
    assert (tmp_path / "jobs.db.v0-20260926_100000.bak").read_text() == "別的檔案"


def test_upgrade_nothing_to_do(tmp_path):
    assert upgrade_db(tmp_path / "沒有這個檔.db") is None
    assert not (tmp_path / "沒有這個檔.db").exists()

    open_db(tmp_path / "jobs.db").close()
    assert upgrade_db(tmp_path / "jobs.db") is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.db"]


def test_open_db_new_is_latest(tmp_path):
    with closing(open_db(tmp_path / "jobs.db")) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION


def test_open_db_latest_does_not_need_write_lock(tmp_path):
    path = tmp_path / "jobs.db"
    open_db(path).close()

    # 其他連線正在寫入時，開啟最新版的資料庫仍然成功，不必等寫入鎖
    with closing(sqlite3.connect(path, timeout=0)) as other:
        other.execute("BEGIN IMMEDIATE")
        with closing(open_db(path)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        other.rollback()


def test_open_db_rejects_old_and_newer(tmp_path, make_job):
    old = _legacy_db(tmp_path / "old.db", LEGACY["有評分來源"][0], make_job)
    newer = tmp_path / "newer.db"
    with closing(sqlite3.connect(newer)) as conn:
        conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 1}")

    with pytest.raises(sqlite3.DatabaseError, match="舊版（第 0 版）"):
        open_db(old)
    with pytest.raises(sqlite3.DatabaseError, match="比這份程式支援的"):
        open_db(newer)
    assert upgrade_db(newer) is None


def test_score_requires_job(db_conn):
    # 評分的職缺都來自職缺資料庫：沒有對應職缺的評分寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        save_auto_score(
            db_conn, job_no="沒有這筆", scored_at=datetime(2026, 9, 20), eliminated=True, total=None,
            comment="淘汰", details={}, provider=None, model=None,
            basis={"偏好版本": 1, "經歷版本": 1, "模板版本": 1, "職缺快照": {}},
        )
