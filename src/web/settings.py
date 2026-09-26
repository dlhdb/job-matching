"""
設定頁的 API：偏好、經歷、提示詞模板的版本紀錄、儲存新版本、套用舊版本、修改名稱與描述，以及編輯時的檢查。

版本只新增、不刪除，所以沒有刪除版本的端點；儲存或套用都不會重評。
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from job_db import add_version, apply_version, current_versions, get_version, list_versions, update_version_meta
from job_scoring.settings import DEFAULTS, KINDS, check, is_default
from web.db import connect

Kind = Literal["preferences", "experience", "template"]

_KIND_NAMES = {"preferences": "偏好", "experience": "經歷", "template": "提示詞模板"}


# ---------------------------------------------------------------------------
# 請求與回應的模型
# ---------------------------------------------------------------------------

class Version(BaseModel):
    version: int
    name: str
    description: str = Field(description="沒有填時是空字串")
    saved_at: str = Field(description="儲存時間，本地時間 ISO 8601，精確到秒")
    content: str


class KindState(BaseModel):
    current: int = Field(description="目前設定是第幾版")
    is_default: bool = Field(description="目前設定的內容是否和專案附的預設內容相同")
    default_content: str = Field(description="專案附的預設內容，「還原預設」用")
    versions: list[Version] = Field(description="由新到舊")


class SettingsState(BaseModel):
    preferences: KindState
    experience: KindState
    template: KindState


class CheckRequest(BaseModel):
    kind: Kind
    content: str


class CheckResult(BaseModel):
    errors: list[str] = Field(description="有錯誤時不能儲存或套用")
    warnings: list[str] = Field(description="提醒，不擋儲存")


class NewVersion(BaseModel):
    name: str = Field(description="必填，頭尾的空白會去掉")
    description: str = Field(default="", description="可以空白")
    content: str


class VersionMeta(BaseModel):
    name: str = Field(description="必填，頭尾的空白會去掉")
    description: str = Field(default="", description="可以空白")


class ApplyVersion(BaseModel):
    version: int


class SavedVersion(BaseModel):
    version: int = Field(description="新版本的編號，已經改成目前設定")


# ---------------------------------------------------------------------------
# 端點
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/settings")


def _version_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": row["版本"], "name": row["名稱"], "description": row["描述"],
        "saved_at": row["儲存時間"], "content": row["內容"],
    }


def _require_valid(kind: str, content: str) -> None:
    """
    :raises HTTPException: 422 內容檢查有錯誤
    """
    errors = check(kind, content).errors
    if errors:
        raise HTTPException(status_code=422, detail=f"{_KIND_NAMES[kind]}有錯，不能儲存或套用：{'；'.join(errors)}")


def _require_name(name: str) -> str:
    """
    :return: str, 去掉頭尾空白的名稱
    :raises HTTPException: 422 名稱是空的
    """
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="版本的名稱必填")
    return name


@router.get(
    "",
    response_model=SettingsState,
    summary="取得三份設定",
    description="偏好、經歷、提示詞模板各自的版本紀錄（由新到舊）、目前設定是哪一版，以及預設內容。",
)
def get_settings(request: Request) -> dict[str, Any]:
    with connect(request) as conn:
        current = current_versions(conn)
        state = {}
        for kind in KINDS:
            state[kind] = {
                "current": current[kind]["版本"],
                "is_default": is_default(kind, current[kind]["內容"]),
                "default_content": DEFAULTS[kind],
                "versions": [_version_out(row) for row in list_versions(conn, kind)],
            }
    return state


@router.post(
    "/check",
    response_model=CheckResult,
    summary="檢查設定的內容",
    description=(
        "編輯時即時檢查：偏好依欄位字典驗證；提示詞模板檢查標記與變數，沒用到的變數只提醒；經歷不檢查。"
    ),
)
def check_content(body: CheckRequest) -> dict[str, Any]:
    result = check(body.kind, body.content)
    return {"errors": result.errors, "warnings": result.warnings}


@router.post(
    "/{kind}/versions",
    status_code=201,
    response_model=SavedVersion,
    summary="儲存並套用新版本",
    description=(
        "把內容存成新版本並改成目前設定；只要送來就新增，即使內容和其他版本相同。"
        "名稱空白或內容檢查有錯時回 422，什麼都不存。"
    ),
)
def save_version(request: Request, kind: Kind, body: NewVersion) -> dict[str, Any]:
    name = _require_name(body.name)
    _require_valid(kind, body.content)
    with connect(request) as conn:
        version = add_version(
            conn, kind, name=name, description=body.description.strip(), content=body.content, saved_at=datetime.now(),
        )
    return {"version": version}


@router.put(
    "/{kind}/current",
    status_code=204,
    summary="套用某一版",
    description="把某一版改成目前設定，不新增版本。沒有這一版時回 404；內容檢查有錯時回 422。",
)
def apply(request: Request, kind: Kind, body: ApplyVersion) -> None:
    with connect(request) as conn:
        row = get_version(conn, kind, body.version)
        if row is None:
            raise HTTPException(status_code=404, detail=f"沒有第 {body.version} 版")
        _require_valid(kind, row["內容"])
        apply_version(conn, kind, body.version)


@router.patch(
    "/{kind}/versions/{version}",
    status_code=204,
    summary="修改版本的名稱與描述",
    description="只改名稱與描述，內容不能改。名稱空白時回 422；沒有這一版時回 404。",
)
def update_meta(request: Request, kind: Kind, version: int, body: VersionMeta) -> None:
    name = _require_name(body.name)
    try:
        with connect(request) as conn:
            update_version_meta(conn, kind, version, name=name, description=body.description.strip())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

