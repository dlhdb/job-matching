"""
職缺資料庫：把每次抓取或匯入的職缺寫進同一個 SQLite 檔，以職缺代碼跨次去重，並記錄每次執行的條件。
"""

from job_db.queries import existing_job_codes, get_job, list_jobs, list_runs
from job_db.schema import DEFAULT_DB_PATH, JOB_COLUMNS, open_db, open_db_readonly
from job_db.scores import (
    get_score, get_score_details, list_scored_jobs, list_scores, list_unscored_jobs, save_auto_score, save_score,
)
from job_db.store import SaveResult, save_run

__all__ = [
    "DEFAULT_DB_PATH", "JOB_COLUMNS", "open_db", "open_db_readonly",
    "SaveResult", "save_run",
    "existing_job_codes", "get_job", "list_jobs", "list_runs",
    "get_score", "list_scored_jobs", "save_score",
    "get_score_details", "list_scores", "list_unscored_jobs", "save_auto_score",
]
