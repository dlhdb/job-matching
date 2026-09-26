"""評分紀錄保存與查詢的離線測試。資料庫建在 tmp_path，評分紀錄寫在測試碼裡，不經過評分流程。"""

import re
from datetime import datetime

import pytest

from job_db import list_current_scores, list_scores, open_db, save_auto_score, save_run

CURRENT_NAMES = ["職缺代碼", "評分時間", "淘汰", "總分", "評語", "供應商", "模型", "評分明細"]

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


def test_list_current_scores_one_per_job(conn, scored):
    rows = list_current_scores(conn)

    # 依職缺代碼排序，每筆職缺一筆
    assert [row["職缺代碼"] for row in rows] == ["high", "low", "out"]
    assert list(rows[0]) == CURRENT_NAMES
    assert re.fullmatch(TIME_PATTERN, rows[0]["評分時間"])
    assert (rows[0]["總分"], rows[0]["評語"]) == (80, "high 的評語")
    assert (rows[0]["供應商"], rows[0]["模型"]) == ("gemini", "測試模型")
    # 評分明細還原成 dict
    assert rows[0]["評分明細"] == {"職缺代碼": "high", "總分": 80}
    assert (rows[2]["淘汰"], rows[2]["總分"]) == (1, None)


def test_list_current_scores_latest_wins(conn, scored):
    # AC-history-current 的資料部分：時間較新的為準；同一秒內後寫入的為準
    write_score(conn, "high", total=50, scored_at=datetime(2026, 9, 16, 10, 0, 0))
    write_score(conn, "low", total=90, scored_at=datetime(2026, 9, 18, 10, 0, 0))
    write_score(conn, "out", total=None, eliminated=False)

    rows = {row["職缺代碼"]: row for row in list_current_scores(conn)}

    assert rows["high"]["總分"] == 80
    assert rows["low"]["總分"] == 90
    assert rows["out"]["淘汰"] == 0


def test_list_current_scores_empty_db_is_empty(conn):
    assert list_current_scores(conn) == []


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
    assert [r["總分"] for r in list_current_scores(conn) if r["職缺代碼"] == "high"] == [50]
