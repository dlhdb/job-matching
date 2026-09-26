"""資料表定義，以及開啟並初始化資料庫。"""

import sqlite3
from pathlib import Path

# 以模組位置為基準，不受執行時的工作目錄影響（data/ 已列入 .gitignore）
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "jobs.db"

# 職缺欄位契約的實作：欄名、順序與 SQL 型態。來源功能整理出來的欄位（例如爬蟲的 parse_job）對齊這份
JOB_COLUMNS: list[tuple[str, str]] = [
    ("職缺代碼", "TEXT"),
    ("職缺名稱", "TEXT"),
    ("公司名稱", "TEXT"),
    ("產業類別", "TEXT"),
    ("地區", "TEXT"),
    ("薪資待遇", "TEXT"),
    ("薪資下限", "INTEGER"),
    ("薪資上限", "INTEGER"),
    ("更新日期", "TEXT"),
    ("應徵人數", "INTEGER"),
    ("工作內容", "TEXT"),
    ("電腦專長", "TEXT"),
    ("科系要求", "TEXT"),
    ("特色標籤", "TEXT"),
    ("職缺連結", "TEXT"),
    ("公司連結", "TEXT"),
]


def _jobs_ddl() -> str:
    """
    產生 jobs 表的建表語法

    :return: str, CREATE TABLE 語法
    """
    columns = [
        f'"{name}" {sql_type} PRIMARY KEY' if name == "職缺代碼" else f'"{name}" {sql_type}'
        for name, sql_type in JOB_COLUMNS
    ]
    columns += ['"首次出現時間" TEXT NOT NULL', '"最後出現時間" TEXT NOT NULL']
    return "CREATE TABLE IF NOT EXISTS jobs (\n    " + ",\n    ".join(columns) + "\n)"


# 資料庫結構的版本，記在 PRAGMA user_version；0 是開始記版本之前的各種舊版，改版見 job_db/upgrade.py
LATEST_VERSION = 1

# 設定的種類：偏好、經歷、提示詞模板
SETTING_KINDS = ("preferences", "experience", "template")

JOB_SCORES_DDL = """
    CREATE TABLE IF NOT EXISTS job_scores (
        "評分編號" INTEGER PRIMARY KEY AUTOINCREMENT,
        "職缺代碼" TEXT NOT NULL REFERENCES jobs("職缺代碼"),
        "評分時間" TEXT NOT NULL,
        "淘汰" INTEGER NOT NULL,
        "總分" INTEGER,
        "評語" TEXT,
        "評分明細" TEXT,
        "供應商" TEXT,
        "模型" TEXT,
        "偏好版本" INTEGER,
        "經歷版本" INTEGER,
        "模板版本" INTEGER,
        "職缺快照" TEXT,
        CHECK (
            ("偏好版本" IS NULL) = ("經歷版本" IS NULL)
            AND ("經歷版本" IS NULL) = ("模板版本" IS NULL)
            AND ("模板版本" IS NULL) = ("職缺快照" IS NULL)
        )
    )
"""

JOB_SCORES_INDEX_DDL = 'CREATE INDEX IF NOT EXISTS job_scores_job ON job_scores("職缺代碼", "評分時間")'

_KIND_CHECK = ", ".join(f"'{kind}'" for kind in SETTING_KINDS)

SETTINGS_DDL = [
    f"""
    CREATE TABLE IF NOT EXISTS settings_versions (
        "種類" TEXT NOT NULL CHECK ("種類" IN ({_KIND_CHECK})),
        "版本" INTEGER NOT NULL,
        "名稱" TEXT NOT NULL,
        "描述" TEXT NOT NULL,
        "儲存時間" TEXT NOT NULL,
        "內容" TEXT NOT NULL,
        PRIMARY KEY ("種類", "版本")
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS current_settings (
        "種類" TEXT PRIMARY KEY,
        "版本" INTEGER NOT NULL,
        FOREIGN KEY ("種類", "版本") REFERENCES settings_versions("種類", "版本")
    )
    """,
]

JOB_DDL = [
    _jobs_ddl(),
    """
    CREATE TABLE IF NOT EXISTS scrape_runs (
        "執行編號" INTEGER PRIMARY KEY AUTOINCREMENT,
        "執行時間" TEXT NOT NULL,
        "來源" TEXT NOT NULL,
        "關鍵字" TEXT,
        "地區" TEXT,
        "職缺性質" INTEGER,
        "頁數" INTEGER,
        "來源檔" TEXT UNIQUE,
        "職缺數" INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_jobs (
        "執行編號" INTEGER NOT NULL REFERENCES scrape_runs("執行編號"),
        "職缺代碼" TEXT NOT NULL REFERENCES jobs("職缺代碼"),
        PRIMARY KEY ("執行編號", "職缺代碼")
    )
    """,
]

# 最新版的完整結構。評分紀錄同一筆職缺可以有多筆，每次評分都新增一筆；設定的每個版本只新增、不刪除
SCHEMA = [*JOB_DDL, JOB_SCORES_DDL, JOB_SCORES_INDEX_DDL, *SETTINGS_DDL]


def db_version(conn: sqlite3.Connection) -> int:
    """
    取出資料庫結構的版本

    :param conn: sqlite3.Connection, 開啟中的連線
    :return: int, PRAGMA user_version 的值
    """
    return conn.execute("PRAGMA user_version").fetchone()[0]


def is_empty(conn: sqlite3.Connection) -> bool:
    """
    是否還沒有任何資料表（剛建立的資料庫檔）

    :param conn: sqlite3.Connection, 開啟中的連線
    :return: bool
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    return row is None


def open_db(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    開啟資料庫；檔案或上層目錄不存在時自動建立，並建立最新版的資料表。

    舊版的資料庫不在這裡改版，要先經過 upgrade_db（網頁啟動時會做）。

    :param path: str or Path, 資料庫檔路徑，預設為專案根目錄的 data/jobs.db
    :return: sqlite3.Connection, 交易需以 commit 或 with 區塊結束
    :raises sqlite3.DatabaseError: 資料庫是舊版或比程式新的版本
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, autocommit=True)
    # 交易中設定 foreign_keys 不會生效，必須在切換成手動交易前設定
    conn.execute("PRAGMA foreign_keys = ON")
    conn.autocommit = False
    try:
        version = db_version(conn)
        if version > LATEST_VERSION:
            raise sqlite3.DatabaseError(
                f"資料庫是第 {version} 版，比這份程式支援的第 {LATEST_VERSION} 版新，請更新程式"
            )
        # 不先擋下的話，舊版的表會被 CREATE TABLE IF NOT EXISTS 略過，查詢到欄位不存在時才失敗
        if version < LATEST_VERSION and not is_empty(conn):
            raise sqlite3.DatabaseError(
                f"資料庫是舊版（第 {version} 版），請先用 uv run src/app.py 啟動網頁，改成第 {LATEST_VERSION} 版"
            )
        with conn:
            for ddl in SCHEMA:
                conn.execute(ddl)
            # 只在剛建立時寫入版本：已是最新版時再寫一次會讓每條連線都要搶寫入鎖
            if version != LATEST_VERSION:
                conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
    except BaseException:
        conn.close()
        raise
    return conn
