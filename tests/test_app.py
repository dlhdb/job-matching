"""網頁進入點的測試：啟動前把舊版資料庫改成最新版，並印出改版結果或失敗原因。uvicorn 以假的函式取代，不真的啟動。"""

import sqlite3
from contextlib import closing

import pytest

import app
import job_db.schema
import job_db.upgrade
from job_db import LATEST_VERSION


@pytest.fixture
def started(monkeypatch):
    """
    以假的 uvicorn.run 記錄啟動的 app

    :return: list, 每次啟動的 (app, host, port)
    """
    calls = []
    monkeypatch.setattr(app.uvicorn, "run", lambda web_app, host, port: calls.append((web_app, host, port)))
    return calls


def _old_db(path, make_job):
    """開始記版本之前的資料庫：一筆職缺、一筆自動評分、一筆手動評分"""
    with closing(sqlite3.connect(path)) as conn, conn:
        for ddl in job_db.schema.JOB_DDL:
            conn.execute(ddl)
        conn.execute('INSERT INTO jobs ("職缺代碼", "首次出現時間", "最後出現時間") VALUES (\'A\', \'t\', \'t\')')
        conn.execute(
            'CREATE TABLE job_scores ("評分編號" INTEGER PRIMARY KEY AUTOINCREMENT, "職缺代碼" TEXT NOT NULL, '
            '"評分來源" TEXT NOT NULL, "評分時間" TEXT NOT NULL, "淘汰" INTEGER NOT NULL, "總分" INTEGER, '
            '"評語" TEXT, "評分明細" TEXT, "供應商" TEXT, "模型" TEXT)'
        )
        conn.execute(
            'INSERT INTO job_scores ("職缺代碼", "評分來源", "評分時間", "淘汰", "總分", "評語", "評分明細") '
            "VALUES ('A', 'auto', 't', 0, 70, '評語', '{}'), ('A', 'manual', 't', 0, 90, '手動', NULL)"
        )
    return path


def test_main_upgrades_before_start(tmp_path, make_job, started, capsys):
    path = _old_db(tmp_path / "jobs.db", make_job)

    assert app.main(path) == 0

    err = capsys.readouterr().err
    assert f"[+] 資料庫已從第 0 版改成第 {LATEST_VERSION} 版，搬移 1 筆評分紀錄" in err
    assert "[!] 略過 1 筆手動評分" in err
    assert "沒有對應的職缺" not in err
    assert f"[i] 改版前的備份：{tmp_path}" in err
    assert len(started) == 1


def test_main_new_db_prints_nothing_about_upgrade(tmp_path, started, capsys):
    assert app.main(tmp_path / "jobs.db") == 0

    assert "改版" not in capsys.readouterr().err
    assert len(started) == 1


def test_main_upgrade_failure(tmp_path, make_job, started, monkeypatch, capsys):
    path = _old_db(tmp_path / "jobs.db", make_job)

    def _fail(conn):
        raise sqlite3.OperationalError("模擬的改版失敗")

    monkeypatch.setattr(job_db.upgrade, "_v0_to_v1", _fail)

    assert app.main(path) == 1

    err = capsys.readouterr().err
    assert "[-] 資料庫改版失敗，資料庫維持改版前的內容：模擬的改版失敗" in err
    assert started == []
