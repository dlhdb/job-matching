"""評分紀錄保存與查詢的離線測試。資料庫建在 tmp_path，評分紀錄寫在測試碼裡。"""

from datetime import datetime

import pytest

from job_db import JOB_COLUMNS, list_scored_jobs, open_db, save_run, save_score

COLUMN_NAMES = [name for name, _ in JOB_COLUMNS]
SCORE_NAMES = ["職缺代碼", "評分時間", "淘汰", "總分", "評語"]

T = datetime(2026, 9, 17, 10, 15, 0)


@pytest.fixture
def conn(tmp_path):
    """
    tmp_path 下已初始化的資料庫連線

    :return: sqlite3.Connection
    """
    connection = open_db(tmp_path / "jobs.db")
    yield connection
    connection.close()


def write_score(conn, job_no, *, total=None, eliminated=False):
    """
    寫入一筆評分紀錄，內容以職缺代碼區分

    :param conn: sqlite3.Connection, 已開啟的連線
    :param job_no: str, 職缺代碼
    :param total: int or None, 總分；被淘汰時為 None
    :param eliminated: bool, 是否被硬性淘汰
    """
    save_score(
        conn,
        job_no=job_no,
        scored_at=T,
        eliminated=eliminated,
        total=total,
        comment=None if eliminated else f"{job_no} 的評語",
        result={"職缺代碼": job_no, "總分": total},
        cache_key=None if eliminated else f"key-{job_no}",
        provider=None if eliminated else "gemini",
        model=None if eliminated else "gemini-3.8-flash",
    )


@pytest.fixture
def scored(conn, make_job):
    """
    三筆評分結果：high 80 分、low 60 分、out 被淘汰；只有 high、out 的職缺資料在資料庫裡

    :return: None
    """
    save_run(conn, [make_job(職缺代碼="high"), make_job(職缺代碼="out")], T, "爬蟲")
    write_score(conn, "high", total=80)
    write_score(conn, "low", total=60)
    write_score(conn, "out", eliminated=True)


def test_list_scored_jobs_orders_by_total(conn, scored):
    rows = list_scored_jobs(conn)

    # 被淘汰的沒有總分，排在最後
    assert [row["職缺代碼"] for row in rows] == ["high", "low", "out"]
    assert [row["總分"] for row in rows] == [80, 60, None]


def test_list_scored_jobs_returns_job_and_score_columns(conn, scored):
    row = list_scored_jobs(conn)[0]

    # 只驗基本欄位都在，產生評分的功能可以在列表疊加欄位
    assert set(COLUMN_NAMES) | set(SCORE_NAMES) <= set(row)
    assert row["職缺名稱"] == "Python 工程師"
    assert row["評分時間"] == T.isoformat(timespec="seconds")
    assert row["評語"] == "high 的評語"


def test_list_scored_jobs_keeps_job_no_without_job_row(conn, scored):
    low = next(row for row in list_scored_jobs(conn) if row["職缺代碼"] == "low")

    # 評分時不必先匯入職缺，職缺欄位為 None，但職缺代碼與評分資訊照常
    assert low["職缺名稱"] is None
    assert low["總分"] == 60 and low["評語"] == "low 的評語"


@pytest.mark.parametrize("eliminated, expected", [
    (True, ["out"]),
    (False, ["high", "low"]),
    (None, ["high", "low", "out"]),
], ids=["only_eliminated", "only_kept", "all"])
def test_list_scored_jobs_filters_by_eliminated(conn, scored, eliminated, expected):
    rows = list_scored_jobs(conn, eliminated=eliminated)

    assert [row["職缺代碼"] for row in rows] == expected


@pytest.mark.parametrize("limit, offset, expected", [
    (1, None, ["high"]),
    (None, 1, ["low", "out"]),
    (1, 1, ["low"]),
    (5, None, ["high", "low", "out"]),
], ids=["limit", "offset_only", "limit_offset", "limit_over_total"])
def test_list_scored_jobs_limit_and_offset(conn, scored, limit, offset, expected):
    rows = list_scored_jobs(conn, limit=limit, offset=offset)

    assert [row["職缺代碼"] for row in rows] == expected


@pytest.mark.parametrize("limit, offset", [(-1, None), (None, -1)], ids=["limit", "offset"])
def test_list_scored_jobs_negative_limit_or_offset_raises(conn, scored, limit, offset):
    with pytest.raises(ValueError):
        list_scored_jobs(conn, limit=limit, offset=offset)


def test_list_scored_jobs_empty_db_is_empty(conn):
    assert list_scored_jobs(conn) == []


def test_record_round_trip_and_overwrite(conn):
    write_score(conn, "kept", total=75)
    write_score(conn, "out", eliminated=True)

    rows = {row["職缺代碼"]: row for row in list_scored_jobs(conn)}
    assert (rows["kept"]["淘汰"], rows["kept"]["總分"], rows["kept"]["評語"]) == (0, 75, "kept 的評語")
    assert (rows["out"]["淘汰"], rows["out"]["總分"]) == (1, None)
    assert rows["kept"]["評分時間"] == T.isoformat(timespec="seconds")

    # 同一個職缺代碼再寫一次，只剩一筆，內容是新的值
    write_score(conn, "kept", total=50)
    kept = [row for row in list_scored_jobs(conn) if row["職缺代碼"] == "kept"]
    assert len(kept) == 1 and kept[0]["總分"] == 50
