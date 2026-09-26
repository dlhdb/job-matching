"""職缺表的 API：列出職缺資料庫的全部職缺，篩選與排序由前端處理。"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import create_model

from job_db import JOB_COLUMNS, list_jobs
from web.db import connect

_SQL_TYPES: dict[str, type] = {"TEXT": str, "INTEGER": int}

# 資料表沒有 NOT NULL 的欄位都可能是 null；這三欄由資料表保證有值
_REQUIRED = {"職缺代碼", "首次出現時間", "最後出現時間"}


def _fields(columns: list[tuple[str, str]]) -> dict[str, Any]:
    """
    把欄名與 SQL 型態轉成 create_model 的欄位定義

    :param columns: list[tuple[str, str]], 欄名與 SQL 型態
    :return: dict, 欄名 -> (型別, ...)，順序同 columns
    """
    fields: dict[str, Any] = {}
    for name, sql_type in columns:
        py_type = _SQL_TYPES[sql_type]
        fields[name] = (py_type, ...) if name in _REQUIRED else (py_type | None, ...)
    return fields


# 職缺欄位契約的欄位，契約只寫在 JOB_COLUMNS 一處；抓取的預覽還沒存入，只有這些欄位
JobFields = create_model("JobFields", **_fields(JOB_COLUMNS))
# 職缺資料庫的一筆職缺：契約欄位，接著是首次、最後出現時間
Job = create_model("Job", __base__=JobFields, **_fields([("首次出現時間", "TEXT"), ("最後出現時間", "TEXT")]))
# Job 是執行時產生的類別，mypy 無法把它當成型別檢查
JobList = create_model("JobList", jobs=(list[Job], ...))  # type: ignore[valid-type]

router = APIRouter(prefix="/api")


@router.get(
    "/jobs",
    response_model=JobList,
    summary="列出全部職缺",
    # 明寫 description，OpenAPI 才不會帶上 docstring 的 :param 等內容
    description="排序為最後出現時間由新到舊；篩選與排序由前端處理。",
)
def get_jobs(request: Request) -> dict[str, Any]:
    """
    列出全部職缺，排序為最後出現時間由新到舊

    :param request: Request, 目前的請求
    :return: dict, {"jobs": [...]}；沒有職缺時為空清單
    """
    with connect(request) as conn:
        return {"jobs": list_jobs(conn)}
