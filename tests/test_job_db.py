"""職缺資料庫的離線測試。資料庫建在 tmp_path，職缺資料寫在測試碼裡。"""

import sqlite3
from datetime import datetime

import pytest

from job_db import JOB_COLUMNS, SaveResult, get_job, list_jobs, list_runs, open_db, save_run

COLUMN_NAMES = [name for name, _ in JOB_COLUMNS]

T1 = datetime(2026, 9, 1, 10, 0, 0)
T2 = datetime(2026, 9, 17, 10, 15, 0)


@pytest.fixture
def conn(tmp_path):
    """
    tmp_path 下已初始化的資料庫連線

    :return: sqlite3.Connection
    """
    connection = open_db(tmp_path / "jobs.db")
    yield connection
    connection.close()


def dump(conn, table):
    """
    依主鍵排序取出整個表的內容

    :return: list[tuple]
    """
    return conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()


def jobs_by_no(conn):
    """
    以職缺代碼為鍵取出 jobs 表

    :return: dict[str, dict]
    """
    cursor = conn.execute("SELECT * FROM jobs")
    names = [d[0] for d in cursor.description]
    return {row[0]: dict(zip(names, row)) for row in cursor}


def columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


# ---------------------------------------------------------------------------
# 開啟資料庫
# ---------------------------------------------------------------------------

def test_open_db_creates_directories_and_tables(tmp_path):
    path = tmp_path / "a" / "b" / "jobs.db"

    connection = open_db(path)

    assert path.is_file()
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"jobs", "scrape_runs", "run_jobs"} <= tables
    assert columns(connection, "jobs") == [*COLUMN_NAMES, "首次出現時間", "最後出現時間"]
    assert columns(connection, "scrape_runs") == [
        "執行編號", "執行時間", "來源", "關鍵字", "地區", "職缺性質", "頁數", "來源檔", "職缺數",
    ]
    assert columns(connection, "run_jobs") == ["執行編號", "職缺代碼"]
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    connection.close()


def test_open_db_job_columns_types():
    int_columns = {name for name, sql_type in JOB_COLUMNS if sql_type == "INTEGER"}
    assert int_columns == {"薪資下限", "薪資上限", "應徵人數"}


def test_open_db_reopen_keeps_data(tmp_path, make_job):
    path = tmp_path / "jobs.db"
    first = open_db(path)
    save_run(first, [make_job()], T1, "爬蟲")
    first.close()

    second = open_db(path)

    assert list(jobs_by_no(second)) == ["ok"]
    second.close()


# ---------------------------------------------------------------------------
# 跨次去重與出現時間
# ---------------------------------------------------------------------------

@pytest.fixture
def two_batches(make_job):
    """
    兩批部分重疊的職缺：a 只在第一批、b 兩批都有、c 只在第二批

    :return: dict[datetime, list[dict]]
    """
    return {
        T1: [make_job(職缺代碼="a"), make_job(職缺代碼="b", 職缺名稱="舊名稱", 應徵人數=1)],
        T2: [make_job(職缺代碼="b", 職缺名稱="新名稱", 應徵人數=9), make_job(職缺代碼="c")],
    }


@pytest.mark.parametrize("order", [(T1, T2), (T2, T1)], ids=["t1_then_t2", "t2_then_t1"])
def test_save_run_dedups_and_tracks_times(conn, two_batches, capsys, order):
    first, second = order

    assert save_run(conn, two_batches[first], first, "爬蟲") == SaveResult(inserted=2, updated=0)
    assert save_run(conn, two_batches[second], second, "爬蟲") == SaveResult(inserted=1, updated=1)

    err = capsys.readouterr().err
    assert "[+] 已寫入資料庫：新增 2 筆、更新 0 筆" in err
    assert "[+] 已寫入資料庫：新增 1 筆、更新 1 筆" in err
    assert "jobs.db" in err

    jobs = jobs_by_no(conn)
    assert sorted(jobs) == ["a", "b", "c"]
    assert (jobs["a"]["首次出現時間"], jobs["a"]["最後出現時間"]) == ("2026-09-01T10:00:00", "2026-09-01T10:00:00")
    assert (jobs["b"]["首次出現時間"], jobs["b"]["最後出現時間"]) == ("2026-09-01T10:00:00", "2026-09-17T10:15:00")
    assert (jobs["c"]["首次出現時間"], jobs["c"]["最後出現時間"]) == ("2026-09-17T10:15:00", "2026-09-17T10:15:00")
    assert jobs["b"]["職缺名稱"] == "新名稱"
    assert jobs["b"]["應徵人數"] == 9


def test_save_run_order_does_not_matter(tmp_path, two_batches):
    results = []
    for name, order in [("forward", (T1, T2)), ("backward", (T2, T1))]:
        connection = open_db(tmp_path / f"{name}.db")
        for t in order:
            save_run(connection, two_batches[t], t, "爬蟲")
        results.append(dump(connection, "jobs"))
        connection.close()

    assert results[0] == results[1]


def test_save_run_same_time_counts_as_update(conn, make_job):
    save_run(conn, [make_job()], T1, "爬蟲")

    assert save_run(conn, [make_job(職缺名稱="改名")], T1, "匯入", source_file="x.json") == SaveResult(0, 1)
    assert jobs_by_no(conn)["ok"]["職缺名稱"] == "改名"


def test_save_run_stores_types(conn, make_job):
    save_run(conn, [make_job(薪資下限=None)], T1, "爬蟲")

    row = conn.execute('SELECT typeof("薪資下限"), typeof("薪資上限"), typeof("應徵人數"), typeof("職缺名稱") FROM jobs').fetchone()
    assert row == ("null", "integer", "integer", "text")


# ---------------------------------------------------------------------------
# null 不覆蓋工作內容與薪資待遇
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("old, new, expected", [
    ("舊值", None, "舊值"),
    ("舊值", "新值", "新值"),
    (None, "新值", "新值"),
])
def test_save_run_keeps_detail_when_new_is_null(conn, make_job, old, new, expected):
    save_run(conn, [make_job(工作內容=old, 薪資待遇=old)], T1, "爬蟲")

    save_run(conn, [make_job(工作內容=new, 薪資待遇=new)], T2, "爬蟲")

    job = jobs_by_no(conn)["ok"]
    assert job["工作內容"] == expected
    assert job["薪資待遇"] == expected


def test_save_run_keeps_detail_only_for_detail_fields(conn, make_job):
    save_run(conn, [make_job()], T1, "爬蟲")

    save_run(conn, [make_job(薪資下限=None, 職缺名稱=None)], T2, "爬蟲")

    job = jobs_by_no(conn)["ok"]
    assert job["薪資下限"] is None
    assert job["職缺名稱"] is None
    assert job["工作內容"] == "工作標記-CCC"


def test_save_run_keeps_detail_older_data_changes_nothing(conn, make_job):
    save_run(conn, [make_job(工作內容=None)], T2, "爬蟲")

    save_run(conn, [make_job(工作內容="舊時間的內容", 職缺名稱="舊名稱")], T1, "爬蟲")

    job = jobs_by_no(conn)["ok"]
    assert job["工作內容"] is None
    assert job["職缺名稱"] == "Python 工程師"
    assert job["首次出現時間"] == "2026-09-01T10:00:00"


# ---------------------------------------------------------------------------
# 執行紀錄與交易
# ---------------------------------------------------------------------------

def test_save_run_records_run(conn, make_job):
    jobs = [make_job(職缺代碼="a"), make_job(職缺代碼="b")]

    save_run(conn, jobs, T2, "爬蟲", keywords="Python, AI", area="台北市", job_type=1, pages=2)

    assert dump(conn, "scrape_runs") == [
        (1, "2026-09-17T10:15:00", "爬蟲", "Python, AI", "台北市", 1, 2, None, 2),
    ]
    assert dump(conn, "run_jobs") == [(1, "a"), (1, "b")]


def test_save_run_records_each_run(conn, make_job):
    save_run(conn, [make_job(職缺代碼="a")], T1, "爬蟲")
    save_run(conn, [make_job(職缺代碼="a"), make_job(職缺代碼="b")], T2, "匯入", source_file="x.json")

    runs = dump(conn, "scrape_runs")
    assert [(r[0], r[2], r[7], r[8]) for r in runs] == [(1, "爬蟲", None, 1), (2, "匯入", "x.json", 2)]
    assert dump(conn, "run_jobs") == [(1, "a"), (2, "a"), (2, "b")]


def test_save_run_rollback_on_error(conn, make_job):
    save_run(conn, [make_job(職缺代碼="a")], T1, "爬蟲")
    before = {table: dump(conn, table) for table in ("jobs", "scrape_runs", "run_jobs")}

    # dict 不是 SQLite 支援的型態，寫到第二筆時會拋出例外
    bad_batch = [make_job(職缺代碼="a", 職缺名稱="改名"), make_job(職缺代碼="b", 地區={"不支援": 1})]
    with pytest.raises(sqlite3.Error):
        save_run(conn, bad_batch, T2, "爬蟲")

    assert {table: dump(conn, table) for table in before} == before


# ---------------------------------------------------------------------------
# 查詢職缺與執行紀錄
# ---------------------------------------------------------------------------

@pytest.fixture
def queried(conn, make_job):
    """
    兩次寫入：t1 寫 a、b，t2 寫 b、c，所以 b 的最後出現時間是 t2

    :return: dict[str, int], 兩次寫入的執行編號，鍵是 "first"、"second"
    """
    save_run(conn, [make_job(職缺代碼="a"), make_job(職缺代碼="b")], T1, "爬蟲", keywords="Python")
    save_run(conn, [make_job(職缺代碼="b"), make_job(職缺代碼="c")], T2, "匯入", source_file="jobs.json")
    ids = [row[0] for row in conn.execute('SELECT "執行編號" FROM scrape_runs ORDER BY "執行編號"')]
    return {"first": ids[0], "second": ids[1]}


def test_list_jobs_orders_by_last_seen(conn, queried):
    rows = list_jobs(conn)

    # b、c 的最後出現時間都是 t2，同時間再比職缺代碼；a 停在 t1，排最後
    assert [row["職缺代碼"] for row in rows] == ["b", "c", "a"]


def test_list_jobs_returns_contract_columns(conn, queried):
    row = list_jobs(conn)[0]

    assert list(row) == [*COLUMN_NAMES, "首次出現時間", "最後出現時間"]
    assert row["最後出現時間"] == T2.isoformat(timespec="seconds")


def test_list_jobs_filters_by_run(conn, queried):
    first = list_jobs(conn, run_id=queried["first"])
    second = list_jobs(conn, run_id=queried["second"])

    assert [row["職缺代碼"] for row in first] == ["b", "a"]
    assert [row["職缺代碼"] for row in second] == ["b", "c"]


def test_list_jobs_unknown_run_is_empty(conn, queried):
    assert list_jobs(conn, run_id=999) == []


def test_list_jobs_empty_db_is_empty(conn):
    assert list_jobs(conn) == []


@pytest.mark.parametrize("limit, offset, expected", [
    (1, None, ["b"]),
    (2, None, ["b", "c"]),
    (None, 1, ["c", "a"]),
    (1, 2, ["a"]),
    (5, None, ["b", "c", "a"]),
], ids=["limit", "limit_2", "offset_only", "limit_offset", "limit_over_total"])
def test_list_jobs_limit_and_offset(conn, queried, limit, offset, expected):
    rows = list_jobs(conn, limit=limit, offset=offset)

    assert [row["職缺代碼"] for row in rows] == expected


@pytest.mark.parametrize("limit, offset", [(-1, None), (None, -1)], ids=["limit", "offset"])
def test_list_jobs_negative_limit_or_offset_raises(conn, queried, limit, offset):
    # SQLite 把負的 LIMIT 當成不限筆數，要擋下來而不是靜默回傳全部
    with pytest.raises(ValueError):
        list_jobs(conn, limit=limit, offset=offset)


def test_get_job_returns_full_row(conn, queried):
    job = get_job(conn, "a")

    assert job is not None
    assert list(job) == [*COLUMN_NAMES, "首次出現時間", "最後出現時間"]
    assert job["職缺名稱"] == "Python 工程師"
    assert job["首次出現時間"] == job["最後出現時間"] == T1.isoformat(timespec="seconds")


def test_get_job_missing_is_none(conn, queried):
    assert get_job(conn, "沒有這筆") is None


def test_list_runs_orders_by_run_time(conn, queried):
    runs = list_runs(conn)

    assert [row["來源"] for row in runs] == ["匯入", "爬蟲"]
    assert [row["職缺數"] for row in runs] == [2, 2]


def test_list_runs_keeps_missing_conditions_null(conn, queried):
    latest, earliest = list_runs(conn)

    # 匯入沒有提供搜尋條件、爬蟲沒有提供來源檔，都不回填
    assert latest["來源檔"] == "jobs.json" and latest["關鍵字"] is None
    assert earliest["關鍵字"] == "Python" and earliest["來源檔"] is None


def test_list_runs_limit(conn, queried):
    assert [row["來源"] for row in list_runs(conn, limit=1)] == ["匯入"]


def test_list_runs_empty_db_is_empty(conn):
    assert list_runs(conn) == []
