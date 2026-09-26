"""評分紀錄保存與查詢的離線測試。資料庫建在 tmp_path，評分紀錄寫在測試碼裡，不經過評分流程。"""

import re
from datetime import datetime

import pytest

from job_db import JOB_COLUMNS, get_score, list_scored_jobs, list_scores, open_db, save_auto_score, save_run

COLUMN_NAMES = [name for name, _ in JOB_COLUMNS]
SCORE_NAMES = ["職缺代碼", "評分時間", "淘汰", "總分", "評語"]

T = datetime(2026, 9, 17, 10, 15, 0)

TIME_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"

BASIS = {"偏好版本": 2, "經歷版本": 3, "模板版本": 1, "職缺快照": {"職缺名稱": "Python 工程師", "薪資下限": 60000}}


@pytest.fixture
def conn(tmp_path):
    """
    tmp_path 下已初始化的資料庫連線

    :return: sqlite3.Connection
    """
    connection = open_db(tmp_path / "jobs.db")
    yield connection
    connection.close()


def write_score(conn, job_no, *, total=None, eliminated=False, scored_at=T):
    """
    寫入一筆評分紀錄，評語以職缺代碼區分

    :param conn: sqlite3.Connection, 已開啟的連線
    :param job_no: str, 職缺代碼
    :param total: int or None, 總分
    :param eliminated: bool, 是否淘汰
    :param scored_at: datetime, 評分時間
    """
    save_auto_score(
        conn, job_no=job_no, scored_at=scored_at, eliminated=eliminated, total=total, comment=f"{job_no} 的評語",
        details={"職缺代碼": job_no, "總分": total}, provider=None if eliminated else "gemini",
        model=None if eliminated else "測試模型", basis=BASIS,
    )


@pytest.fixture
def scored(conn, make_job):
    """
    三筆評分紀錄：high 80 分、low 60 分、out 被淘汰且沒有總分

    :return: None
    """
    save_run(conn, [make_job(職缺代碼=code) for code in ("high", "low", "out")], T, "爬蟲")
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

    assert set(COLUMN_NAMES) | set(SCORE_NAMES) <= set(row)
    assert row["職缺名稱"] == "Python 工程師"
    assert re.fullmatch(TIME_PATTERN, row["評分時間"])
    assert row["評語"] == "high 的評語"
    assert (row["供應商"], row["模型"]) == ("gemini", "測試模型")


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


def test_record_round_trip(conn, scored):
    [record] = list_scores(conn, "high")

    assert (record["淘汰"], record["總分"], record["評語"]) == (0, 80, "high 的評語")
    assert record["評分時間"] == T.isoformat()
    assert record["評分明細"] == {"職缺代碼": "high", "總分": 80}
    # 評分依據原樣保存，快照還原成 dict
    assert {name: record[name] for name in BASIS} == BASIS

    [out] = list_scores(conn, "out")
    assert (out["淘汰"], out["總分"], out["供應商"], out["模型"]) == (1, None, None, None)


def test_record_appends_without_overwrite(conn, scored):
    write_score(conn, "high", total=50, scored_at=datetime(2026, 9, 18, 10, 0, 0))

    assert [r["總分"] for r in list_scores(conn, "high")] == [50, 80]
    assert [r["總分"] for r in list_scored_jobs(conn) if r["職缺代碼"] == "high"] == [50]


def test_get_score_returns_record(conn, scored):
    record = get_score(conn, "out")

    assert list(record) == SCORE_NAMES
    assert (record["職缺代碼"], record["淘汰"], record["總分"], record["評語"]) == ("out", 1, None, "out 的評語")


def test_get_score_missing_is_none(conn, scored):
    assert get_score(conn, "沒有這筆") is None
