"""
職缺資料庫：把每次抓取的職缺寫進同一個 SQLite 檔，以職缺代碼跨次去重，並記錄每次執行的條件；
評分紀錄與評分用的設定也存在同一個檔案。
"""

from job_db.queries import existing_job_codes, get_job, list_jobs, list_runs
from job_db.schema import DEFAULT_DB_PATH, JOB_COLUMNS, LATEST_VERSION, SETTING_KINDS, open_db
from job_db.scores import get_score, get_score_details, list_scored_jobs, list_scores, save_auto_score
from job_db.settings import (
    add_version, apply_version, current_versions, get_version, init_defaults, list_versions, update_version_meta,
)
from job_db.store import SaveResult, save_run
from job_db.upgrade import UpgradeError, UpgradeResult, upgrade_db

__all__ = [
    "DEFAULT_DB_PATH", "JOB_COLUMNS", "LATEST_VERSION", "SETTING_KINDS", "open_db",
    "UpgradeError", "UpgradeResult", "upgrade_db",
    "SaveResult", "save_run",
    "existing_job_codes", "get_job", "list_jobs", "list_runs",
    "get_score", "get_score_details", "list_scored_jobs", "list_scores", "save_auto_score",
    "add_version", "apply_version", "current_versions", "get_version", "init_defaults", "list_versions",
    "update_version_meta",
]
