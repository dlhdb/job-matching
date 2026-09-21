"""評分紀錄保存與查詢的離線測試。資料庫建在 tmp_path，評分紀錄寫在測試碼裡。"""

import re
from datetime import datetime

import pytest

from job_db import JOB_COLUMNS, get_score, list_scored_jobs, open_db, save_run, save_score

COLUMN_NAMES = [name for name, _ in JOB_COLUMNS]
SCORE_NAMES = ["職缺代碼", "評分時間", "淘汰", "總分", "評語"]

T = datetime(2026, 9, 17, 10, 15, 0)

# 評分時間由寫入當下決定，只驗格式：本地時間，ISO 8601，精確到秒
TIME_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"


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
    寫入一筆評分紀錄，評語以職缺代碼區分

    :param conn: sqlite3.Connection, 已開啟的連線
    :param job_no: str, 職缺代碼
    :param total: int or None, 總分
    :param eliminated: bool, 是否淘汰
    """
    save_score(conn, job_no=job_no, comment=f"{job_no} 的評語", total=total, eliminated=eliminated)


@pytest.fixture
def scored(conn, make_job):
    """
    三筆評分紀錄：high 80 分、low 60 分、out 被淘汰且沒有總分；只有 high、out 的職缺資料在資料庫裡

    :return: None
    """
    save_run(conn, [make_job(職缺代碼="high"), make_job(職缺代碼="out")], T, "爬蟲")
    write_score(conn, "high", total=80)
    write_score(conn, "low", total=60)
    write_score(conn, "out", eliminated=True)


def test_list_scored_jobs_orders_by_total(conn, scored):
    rows = list_scored_jobs(conn)

    # 沒有總分的排在最後
    assert [row["職缺代碼"] for row in rows] == ["high", "low", "out"]
    assert [row["總分"] for row in rows] == [80, 60, None]


def test_list_scored_jobs_returns_job_and_score_columns(conn, scored):
    row = list_scored_jobs(conn)[0]

    # 只驗基本欄位都在，產生評分的功能可以在列表疊加欄位
    assert set(COLUMN_NAMES) | set(SCORE_NAMES) <= set(row)
    assert row["職缺名稱"] == "Python 工程師"
    assert re.fullmatch(TIME_PATTERN, row["評分時間"])
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
    assert (rows["out"]["淘汰"], rows["out"]["總分"], rows["out"]["評語"]) == (1, None, "out 的評語")
    assert all(re.fullmatch(TIME_PATTERN, row["評分時間"]) for row in rows.values())

    # 同一個職缺代碼再寫一次，只剩一筆，內容是新的值
    write_score(conn, "kept", total=50)
    kept = [row for row in list_scored_jobs(conn) if row["職缺代碼"] == "kept"]
    assert len(kept) == 1 and kept[0]["總分"] == 50


def test_save_score_manual_write_defaults_and_overwrite(conn):
    before = datetime.now().replace(microsecond=0)
    save_score(conn, job_no="a", comment="第一次的評語")
    after = datetime.now()

    # (a) 只給職缺代碼與評語：總分為 None、淘汰為否、評分時間是寫入當下
    [row] = list_scored_jobs(conn)
    assert (row["職缺代碼"], row["總分"], row["淘汰"], row["評語"]) == ("a", None, 0, "第一次的評語")
    assert before <= datetime.fromisoformat(row["評分時間"]) <= after

    # (b) 同一個職缺代碼再寫一次，只剩一筆，淘汰與總分可以同時有值
    save_score(conn, job_no="a", comment="第二次的評語", total=80, eliminated=True)
    [row] = list_scored_jobs(conn)
    assert (row["職缺代碼"], row["總分"], row["淘汰"], row["評語"]) == ("a", 80, 1, "第二次的評語")


@pytest.mark.parametrize("fields, bad_field", [
    ({"comment": None}, "評語"),
    ({"comment": ""}, "評語"),
    ({"comment": "   "}, "評語"),
    ({"comment": "評語", "total": 101}, "總分"),
    ({"comment": "評語", "total": -1}, "總分"),
    ({"comment": "評語", "total": True}, "總分"),
    ({"comment": "評語", "job_no": ""}, "職缺代碼"),
], ids=["missing_comment", "empty_comment", "blank_comment", "total_101", "total_negative", "total_bool", "empty_job_no"])
def test_save_score_manual_check_rejects_invalid(conn, fields, bad_field):
    save_score(conn, job_no="a", comment="原本的評語", total=70)
    original = get_score(conn, "a")

    with pytest.raises(ValueError, match=bad_field):
        save_score(conn, **{"job_no": "a", **fields})

    # 拒絕時資料庫不變
    assert [row["職缺代碼"] for row in list_scored_jobs(conn)] == ["a"]
    assert get_score(conn, "a") == original


@pytest.mark.parametrize("total", [0, 100], ids=["min", "max"])
def test_save_score_manual_check_accepts_bounds(conn, total):
    save_score(conn, job_no="a", comment="評語", total=total)

    assert get_score(conn, "a")["總分"] == total


def test_get_score_returns_record(conn):
    save_score(conn, job_no="a", comment="評語", total=80, eliminated=True)

    record = get_score(conn, "a")

    assert set(SCORE_NAMES) <= set(record)
    assert (record["職缺代碼"], record["淘汰"], record["總分"], record["評語"]) == ("a", 1, 80, "評語")
    assert record["評分時間"] == list_scored_jobs(conn)[0]["評分時間"]


def test_get_score_missing_is_none(conn):
    save_score(conn, job_no="a", comment="評語")

    assert get_score(conn, "沒有這筆") is None
