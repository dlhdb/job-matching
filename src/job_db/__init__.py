"""
職缺資料庫：把每次抓取或匯入的職缺寫進同一個 SQLite 檔，以職缺代碼跨次去重，並記錄每次執行的條件。
"""

from job_db.schema import DEFAULT_DB_PATH, JOB_COLUMNS, open_db
from job_db.scores import load_cached_result, save_score
from job_db.store import SaveResult, save_run

__all__ = [
    "DEFAULT_DB_PATH", "JOB_COLUMNS", "open_db",
    "SaveResult", "save_run",
    "load_cached_result", "save_score",
]
