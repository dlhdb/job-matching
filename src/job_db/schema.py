"""資料表定義，以及開啟並初始化資料庫。"""

import sqlite3
from pathlib import Path

# 以模組位置為基準，不受執行時的工作目錄影響（data/ 已列入 .gitignore）
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "jobs.db"

# 職缺欄位契約的實作：欄名、順序與 SQL 型態。來源功能自己的欄名（例如爬蟲的 CSV_FIELDNAMES）對齊這份
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


SCHEMA = [
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
    # 評分紀錄，同一筆職缺可以有多筆：自動評分每次新增一筆，手動評分每筆職缺最多一筆；
    # 不設外鍵，評分的職缺不一定匯入過 jobs
    """
    CREATE TABLE IF NOT EXISTS job_scores (
        "評分編號" INTEGER PRIMARY KEY AUTOINCREMENT,
        "職缺代碼" TEXT NOT NULL,
        "評分來源" TEXT NOT NULL CHECK ("評分來源" IN ('auto', 'manual')),
        "評分時間" TEXT NOT NULL,
        "淘汰" INTEGER NOT NULL,
        "總分" INTEGER,
        "評語" TEXT,
        "評分明細" TEXT,
        "快取鍵" TEXT,
        "供應商" TEXT,
        "模型" TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS job_scores_manual
        ON job_scores("職缺代碼") WHERE "評分來源" = 'manual'
    """,
    'CREATE INDEX IF NOT EXISTS job_scores_job ON job_scores("職缺代碼", "評分時間")',
]


def _check_job_scores(conn: sqlite3.Connection) -> None:
    """
    檢查既有的 job_scores 不是舊版（沒有評分來源）；舊版不遷移，要刪除資料庫後重建

    SQLite 把找不到的雙引號欄名當成字串，不先擋下的話，查詢會靜默查不到、寫入到最後才失敗。

    :param conn: sqlite3.Connection, 開啟中的連線
    :raises sqlite3.DatabaseError: job_scores 是舊版
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(job_scores)")}
    if columns and "評分來源" not in columns:
        raise sqlite3.DatabaseError("評分紀錄的資料表是舊版，不支援遷移，請刪除資料庫檔後重建")


def open_db(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    開啟資料庫；檔案或上層目錄不存在時自動建立，並建立缺少的資料表。

    :param path: str or Path, 資料庫檔路徑，預設為專案根目錄的 data/jobs.db
    :return: sqlite3.Connection, 交易需以 commit 或 with 區塊結束
    :raises sqlite3.DatabaseError: 評分紀錄的資料表是舊版
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, autocommit=True)
    # 交易中設定 foreign_keys 不會生效，必須在切換成手動交易前設定
    conn.execute("PRAGMA foreign_keys = ON")
    conn.autocommit = False
    try:
        _check_job_scores(conn)
        with conn:
            for ddl in SCHEMA:
                conn.execute(ddl)
    except BaseException:
        conn.close()
        raise
    return conn
