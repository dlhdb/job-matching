"""
抓取頁的 API：在背景向 104 抓取職缺，抓完先預覽，再整批存入職缺資料庫或捨棄。

沒存入的抓取結果只留在記憶體，直到存入、捨棄或開始新的抓取；web app 關閉時一起消失。
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from fetch_104_jobs import AREAS, DetailProgress, SearchProgress, parse_keywords, scrape
from job_db import existing_job_codes, save_run
from web.db import connect
from web.job_table import JobFields
from web.jobs import Job, JobBusy, JobRunner

KIND = "抓取"
ALL_AREAS = "全台灣"


@dataclass
class Preview:
    """沒存入的抓取結果與這次的條件"""

    jobs: list[dict[str, Any]]
    found: int
    stopped: bool
    finished_at: datetime
    keywords: list[str]
    area: str  # 縣市名稱，或「全台灣」
    job_type: int
    pages: int


class CrawlSession:
    """抓取頁的狀態：沒存入的預覽，以及沒有預覽時最近一次抓取的結果訊息"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.preview: Preview | None = None
        self.outcome: str | None = None


# ---------------------------------------------------------------------------
# 請求與回應的模型
# ---------------------------------------------------------------------------

class CrawlRequest(BaseModel):
    keyword: str = Field(description="多個關鍵字以半形或全形逗號分隔")
    area: str | None = Field(default=None, description="縣市名稱；null 代表全台灣")
    pages: int = Field(ge=1, description="每個關鍵字抓幾頁，每頁 30 筆")
    job_type: Literal[0, 1, 2] = Field(description="職缺性質：0 全部、1 全職、2 兼職／工讀")
    discard_preview: bool = Field(default=False, description="有沒存入的抓取結果時，確認捨棄它")


class SearchProgressOut(BaseModel):
    stage: Literal["search"] = "search"
    keyword: str
    page: int
    pages: int
    found: int


class DetailProgressOut(BaseModel):
    stage: Literal["detail"] = "detail"
    index: int
    total: int


class Running(BaseModel):
    progress: SearchProgressOut | DetailProgressOut | None = Field(description="還沒送出第一個請求時為 null")
    stopping: bool


class PreviewOut(BaseModel):
    # JobFields 是執行時產生的類別，mypy 無法把它當成型別檢查
    jobs: list[JobFields]  # type: ignore[valid-type]
    new_codes: list[str] = Field(description="職缺資料庫裡還沒有的職缺代碼")
    found: int
    stopped: bool


class CrawlState(BaseModel):
    running: Running | None = Field(description="沒在抓取時為 null")
    preview: PreviewOut | None = Field(description="沒有沒存入的抓取結果時為 null")
    outcome: str | None = Field(description="沒有預覽時，最近一次抓取的結果訊息")


class AreaList(BaseModel):
    areas: list[str]


class SavedCodes(BaseModel):
    codes: list[str] = Field(description="這次存入的職缺代碼，順序同預覽")


# ---------------------------------------------------------------------------
# 端點
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/crawl")


def _session(request: Request) -> CrawlSession:
    session: CrawlSession = request.app.state.crawl
    return session


def _runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


def _progress_out(progress: Any) -> SearchProgressOut | DetailProgressOut | None:
    if isinstance(progress, SearchProgress):
        return SearchProgressOut(
            keyword=progress.keyword, page=progress.page, pages=progress.pages, found=progress.found
        )
    if isinstance(progress, DetailProgress):
        return DetailProgressOut(index=progress.index, total=progress.total)
    return None


@router.get(
    "/areas",
    response_model=AreaList,
    summary="列出可以選的縣市",
    description="104 的 22 個縣市，依縣市選單的順序；不選代表全台灣。",
)
def get_areas() -> dict[str, Any]:
    return {"areas": list(AREAS)}


@router.get(
    "",
    response_model=CrawlState,
    summary="取得抓取的狀態",
    description="抓取中的進度、沒存入的抓取結果，或最近一次抓取沒有結果的原因。",
)
def get_state(request: Request) -> dict[str, Any]:
    """
    取得抓取的狀態；預覽的「新」每次都依職缺資料庫重新判斷

    :param request: Request, 目前的請求
    :return: dict, CrawlState
    """
    job = _runner(request).current()
    running = None
    if job is not None and job.kind == KIND:
        running = {"progress": _progress_out(job.progress), "stopping": job.stopping}

    session = _session(request)
    with session.lock:
        preview, outcome = session.preview, session.outcome
    preview_out = None
    if preview is not None:
        codes = [j["職缺代碼"] for j in preview.jobs]
        with connect(request) as conn:
            existing = existing_job_codes(conn, codes)
        preview_out = {
            "jobs": preview.jobs,
            "new_codes": [c for c in codes if c not in existing],
            "found": preview.found,
            "stopped": preview.stopped,
        }
    return {"running": running, "preview": preview_out, "outcome": outcome}


def _crawl(session: CrawlSession, body: CrawlRequest, keywords: list[str]) -> Any:
    """
    產生抓取作業的 target：抓完或停止後，把結果交給 session

    :return: callable, target(job)
    """
    area = body.area or ALL_AREAS

    def target(job: Job) -> None:
        def on_progress(progress: Any) -> None:
            job.progress = progress

        try:
            result = scrape(
                keywords, body.pages, AREAS.get(area), body.job_type, stop=job.stop, on_progress=on_progress
            )
        except Exception as e:
            with session.lock:
                session.outcome = f"抓取失敗：{e}"
            raise
        with session.lock:
            if result.jobs:
                session.preview = Preview(
                    jobs=result.jobs,
                    found=result.found,
                    stopped=result.stopped,
                    finished_at=result.finished_at,
                    keywords=keywords,
                    area=area,
                    job_type=body.job_type,
                    pages=body.pages,
                )
            elif result.stopped:
                session.outcome = "已停止，還沒有取完內容的職缺。"
            else:
                session.outcome = "沒有抓到職缺。"

    return target


@router.post(
    "",
    status_code=202,
    summary="開始抓取",
    description=(
        "在背景開始抓取，進度以 GET /api/crawl 取得。"
        "已有作業在跑，或有沒存入的抓取結果但沒有確認捨棄時回 409；開始時才捨棄舊的結果。"
    ),
)
def start_crawl(request: Request, body: CrawlRequest) -> None:
    """
    驗證條件後在背景開始抓取

    :param request: Request, 目前的請求
    :param body: CrawlRequest, 抓取的條件
    :raises HTTPException: 422 條件不合法；409 已有作業在跑，或有沒存入的結果但沒有確認捨棄
    """
    keywords = parse_keywords(body.keyword)
    if not keywords:
        raise HTTPException(status_code=422, detail="至少要有一個關鍵字")
    if body.area is not None and body.area not in AREAS:
        raise HTTPException(status_code=422, detail=f"不認得的縣市：{body.area}")

    runner, session = _runner(request), _session(request)
    with session.lock:
        running = runner.current()
        if running is not None:
            raise HTTPException(status_code=409, detail=str(JobBusy(running.kind)))
        if session.preview is not None and not body.discard_preview:
            raise HTTPException(status_code=409, detail="還有沒存入的抓取結果，要先存入或確認捨棄")
        try:
            # 抓取的執行緒要拿到 session.lock 才能交出結果，所以一定在下面清空之後
            runner.start(KIND, _crawl(session, body, keywords))
        except JobBusy as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        session.preview = None
        session.outcome = None


@router.post(
    "/stop",
    status_code=204,
    summary="停止抓取",
    description="不再發出新的請求，已送出的請求照常完成；取完內容的職缺進入預覽。",
)
def stop_crawl(request: Request) -> None:
    _runner(request).stop(KIND)


@router.post(
    "/save",
    response_model=SavedCodes,
    summary="存入抓取結果",
    description=(
        "把預覽的職缺整批寫入職缺資料庫，執行時間是抓完或停止的時間。"
        "成功時清掉預覽；寫入失敗時回 500，資料庫與預覽都不變。"
    ),
)
def save_preview(request: Request) -> dict[str, Any]:
    """
    把預覽整批存入職缺資料庫，連同這次的抓取條件

    :param request: Request, 目前的請求
    :return: dict, SavedCodes
    :raises HTTPException: 409 沒有預覽；500 寫入失敗
    """
    session = _session(request)
    with session.lock:
        preview = session.preview
        if preview is None:
            raise HTTPException(status_code=409, detail="沒有要存入的抓取結果")
        try:
            with connect(request) as conn:
                save_run(
                    conn,
                    preview.jobs,
                    preview.finished_at,
                    "爬蟲",
                    keywords=", ".join(preview.keywords),
                    area=preview.area,
                    job_type=preview.job_type,
                    pages=preview.pages,
                )
        except (sqlite3.Error, OSError) as e:
            raise HTTPException(status_code=500, detail=f"存入失敗：{e}") from e
        session.preview = None
    return {"codes": [job["職缺代碼"] for job in preview.jobs]}


@router.delete(
    "/preview",
    status_code=204,
    summary="捨棄抓取結果",
    description="清掉沒存入的抓取結果，職缺資料庫不變。",
)
def discard_preview(request: Request) -> None:
    session = _session(request)
    with session.lock:
        session.preview = None
        session.outcome = None
