"""
試跑的 API：用設定頁編輯區的內容評試跑清單的職缺，不寫入評分紀錄，和目前的評分並排比較。

試跑作業照清單的顯示順序逐筆評，進度與每筆的結果只留在記憶體；作業結束後保留最近一次的結果，
下一次試跑或 web app 關閉時消失。結束後要不要顯示由設定頁決定：只顯示打開期間看過它在跑的試跑。
"""

import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from job_db import get_job, get_version
from job_scoring.batch import score_batch
from job_scoring.llm import DEFAULT_PROVIDER, MODELS, LLMError, api_key_missing, get_client
from job_scoring.models import BatchResult
from job_scoring.rules import check_hard_filters
from job_scoring.settings import KIND_NAMES, KINDS, ScoringSettings, SettingsError, from_contents
from web.db import connect
from web.jobs import Job, JobBusy, JobRunner
from web.scoring import ScoreDetails

KIND = "試跑"

RowState = Literal["queued", "scoring", "done", "failed", "skipped"]


@dataclass
class Row:
    """試跑清單中一筆職缺的狀態與結果"""

    status: RowState = "queued"
    reason: str | None = None
    result: dict[str, Any] | None = None


@dataclass
class Run:
    """一次試跑：用的設定與模型、將評的職缺，以及每筆的狀態與結果"""

    id: int
    model: str
    settings: dict[str, dict[str, Any]]
    codes: list[str]
    rows: dict[str, Row]
    done: int = 0
    stopped: bool = False
    error: str | None = None


@dataclass
class DryRunSession:
    """試跑作業的狀態：在跑的試跑與最近一次結束的試跑"""

    lock: threading.Lock = field(default_factory=threading.Lock)
    last_id: int = 0
    running: Run | None = None
    last: Run | None = None


# ---------------------------------------------------------------------------
# 請求與回應的模型
# ---------------------------------------------------------------------------

class DraftIn(BaseModel):
    base: int = Field(description="編輯區以哪一版為底")
    content: str = Field(description="編輯區目前的內容")


class DraftsIn(BaseModel):
    preferences: DraftIn
    experience: DraftIn
    template: DraftIn


class DraftRef(BaseModel):
    base: int
    name: str = Field(description="base 那一版的名稱")
    modified: bool = Field(description="編輯區的內容和 base 那一版不同")


class DraftOut(DraftRef):
    content: str = Field(description="試跑用的內容；和編輯區比較，就知道試跑後改過沒有")


class DryRunPlanRequest(BaseModel):
    codes: list[str] = Field(description="試跑清單的職缺代碼，依清單的顯示順序")
    settings: DraftsIn = Field(description="三份設定編輯區的內容")


class DryRunStartRequest(DryRunPlanRequest):
    model: str


class DryRunPlan(BaseModel):
    count: int = Field(description="將試跑幾筆")
    eliminated: int | None = Field(description="其中幾筆符合淘汰條件；偏好有錯時為 null")
    settings: dict[str, DraftRef] = Field(description="preferences、experience、template 各用編輯區的什麼內容")
    provider: str
    models: list[str] = Field(description="可以選的模型，第一個是預設")
    errors: list[str] = Field(description="開始前的錯誤；有錯誤時不能開始")


class DryRunStarted(BaseModel):
    run_id: int


class DryRunRow(BaseModel):
    code: str
    status: RowState
    reason: str | None = Field(description="試跑失敗的原因")
    result: ScoreDetails | None = Field(description="試跑的評分結果；還沒評完或失敗時為 null")


class DryRunOut(BaseModel):
    id: int
    total: int
    done: int = Field(description="評完幾筆，含失敗")
    model: str
    settings: dict[str, DraftOut] = Field(description="preferences、experience、template 各用了什麼內容")
    stopping: bool
    stopped: bool = Field(description="按了停止，或因為錯誤而停止")
    error: str | None = Field(description="讓試跑停止的錯誤")
    rows: list[DryRunRow] = Field(description="依試跑的順序")


class DryRunState(BaseModel):
    running: DryRunOut | None = Field(description="沒在試跑時為 null")
    last: DryRunOut | None = Field(description="最近一次結束的試跑；web app 啟動後還沒試跑過時為 null")
    busy: str | None = Field(description="正在跑的其他作業，例如「評分」")


# ---------------------------------------------------------------------------
# 確認與作業
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


def _session(request: Request) -> DryRunSession:
    session: DryRunSession = request.app.state.dry_run
    return session


def _runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


@dataclass
class _Checked:
    """開始前的檢查：確認視窗要顯示的內容，以及開始試跑要用的設定與職缺"""

    plan: dict[str, Any]
    settings: ScoringSettings | None
    drafts: dict[str, dict[str, Any]]
    jobs: list[dict[str, Any]]


def _check(conn: sqlite3.Connection, codes: list[str], drafts: DraftsIn) -> _Checked:
    """
    依編輯區的內容算出試跑的筆數與淘汰筆數，並做開始前的檢查（不含是否有其他作業在跑）。
    偏好或經歷是預設範例時不擋：試跑不影響正式分數。

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param codes: list[str], 試跑清單的職缺代碼，依清單的顯示順序
    :param drafts: DraftsIn, 三份設定編輯區的內容
    :return: _Checked
    """
    codes = list(dict.fromkeys(codes))
    errors: list[str] = []
    jobs = [job for code in codes if (job := get_job(conn, code)) is not None]
    if len(jobs) < len(codes):
        errors.append(f"有 {len(codes) - len(jobs)} 筆試跑清單的職缺不在職缺資料庫中，請重新整理頁面")
    if not codes:
        errors.append("試跑清單是空的：到職缺表勾選職缺後按「加入試跑清單」")

    refs: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        draft = getattr(drafts, kind)
        version = get_version(conn, kind, draft.base)
        if version is None:
            errors.append(f"{KIND_NAMES[kind]}的第 {draft.base} 版不存在，請重新整理頁面")
            continue
        refs[kind] = {
            "base": draft.base,
            "name": version["名稱"],
            "modified": draft.content != version["內容"],
            "content": draft.content,
        }

    try:
        settings: ScoringSettings | None = from_contents(
            {kind: getattr(drafts, kind).content for kind in KINDS},
            {kind: getattr(drafts, kind).base for kind in KINDS},
        )
    except SettingsError as e:
        settings = None
        errors.extend(f"編輯區有錯，先修正再試跑。{message}" for message in e.messages)

    eliminated = None
    if settings is not None:
        eliminated = sum(1 for job in jobs if check_hard_filters(job, settings.preferences))
    # 偏好有錯、算不出淘汰筆數時，當作每一筆都要呼叫 AI
    needs_ai = len(jobs) - (eliminated or 0)
    if needs_ai > 0 and api_key_missing(DEFAULT_PROVIDER):
        errors.append(
            f"沒有設定 API key：有 {needs_ai} 筆需要呼叫 AI，請在專案根目錄的 .env 設定 GEMINI_API_KEY（範本見 .env.example）"
        )

    plan = {
        "count": len(jobs),
        "eliminated": eliminated,
        "settings": {kind: {k: v for k, v in ref.items() if k != "content"} for kind, ref in refs.items()},
        "provider": DEFAULT_PROVIDER,
        "models": MODELS[DEFAULT_PROVIDER],
        "errors": errors,
    }
    return _Checked(plan=plan, settings=settings, drafts=refs, jobs=jobs)


def _run_out(run: Run, stopping: bool) -> dict[str, Any]:
    return {
        "id": run.id,
        "total": len(run.codes),
        "done": run.done,
        "model": run.model,
        "settings": run.settings,
        "stopping": stopping,
        "stopped": run.stopped,
        "error": run.error,
        "rows": [
            {"code": code, "status": row.status, "reason": row.reason, "result": row.result}
            for code in run.codes
            for row in [run.rows[code]]
        ],
    }


def _dry_run(session: DryRunSession, run: Run, jobs: list[dict[str, Any]], settings: ScoringSettings) -> Any:
    """
    產生試跑作業的 target：照順序逐筆評、不寫入，結束時把這次的結果交給 session

    :return: callable, target(job)
    """

    def on_start(_: int, job: dict[str, Any]) -> None:
        with session.lock:
            run.rows[job["職缺代碼"]].status = "scoring"

    def on_result(_: int, result: BatchResult) -> None:
        with session.lock:
            run.done += 1
            row = run.rows[result.job_no]
            if result.failure is not None:
                row.status, row.reason = "failed", result.failure
                return
            row.status = "done"
            row.result = result.model_dump(by_alias=True, exclude={"failure"})

    def target(job: Job) -> None:
        try:
            score_batch(
                jobs, settings, lambda: get_client(DEFAULT_PROVIDER, run.model),
                conn=None, provider=DEFAULT_PROVIDER, model=run.model,
                should_stop=job.stop.is_set, on_start=on_start, on_result=on_result,
            )
        except LLMError as e:
            with session.lock:
                run.error = f"無法開始試跑：{e}"
        except Exception as e:
            with session.lock:
                for row in run.rows.values():
                    if row.status == "scoring":
                        row.status, row.reason = "failed", f"試跑中發生錯誤：{e}"
                        run.done += 1
                run.error = f"試跑中發生錯誤，已停止：{e}"
            raise
        finally:
            with session.lock:
                for row in run.rows.values():
                    if row.status in ("queued", "scoring"):
                        row.status = "skipped"
                run.stopped = job.stopping or run.error is not None
                session.running = None
                session.last = run

    return target


# ---------------------------------------------------------------------------
# 端點
# ---------------------------------------------------------------------------

@router.post(
    "/dry-run/plan",
    response_model=DryRunPlan,
    summary="試跑前的確認",
    description="確認視窗用：將試跑幾筆、其中幾筆淘汰、用編輯區的什麼內容，以及開始前的錯誤。",
)
def plan_dry_run(request: Request, body: DryRunPlanRequest) -> dict[str, Any]:
    with connect(request) as conn:
        plan = _check(conn, body.codes, body.settings).plan
    running = _runner(request).current()
    if running is not None:
        plan["errors"].append(str(JobBusy(running.kind)))
    return plan


@router.post(
    "/dry-run",
    status_code=202,
    response_model=DryRunStarted,
    summary="開始試跑",
    description=(
        "重做開始前的檢查，有錯時回 422（detail 是錯誤清單）；已有作業在跑時回 409。"
        "通過後在背景照 codes 的順序逐筆評，不寫入評分紀錄；進度與結果以 GET /api/dry-run 取得。"
    ),
)
def start_dry_run(request: Request, body: DryRunStartRequest) -> dict[str, Any]:
    if body.model not in MODELS[DEFAULT_PROVIDER]:
        raise HTTPException(status_code=422, detail=[f"不認得的模型：{body.model}"])
    runner, session = _runner(request), _session(request)
    with connect(request) as conn:
        checked = _check(conn, body.codes, body.settings)
    if checked.plan["errors"]:
        raise HTTPException(status_code=422, detail=checked.plan["errors"])
    assert checked.settings is not None

    codes = [job["職缺代碼"] for job in checked.jobs]
    with session.lock:
        run = Run(
            id=session.last_id + 1, model=body.model, settings=checked.drafts,
            codes=codes, rows={code: Row() for code in codes},
        )
        try:
            # 作業的執行緒要拿到 session.lock 才能更新狀態，所以一定在下面設定 running 之後
            runner.start(KIND, _dry_run(session, run, checked.jobs, checked.settings))
        except JobBusy as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        session.last_id = run.id
        session.running = run
    return {"run_id": run.id}


@router.get(
    "/dry-run",
    response_model=DryRunState,
    summary="取得試跑的狀態",
    description="試跑中的進度與每筆的結果、最近一次結束的試跑，以及正在跑的其他作業。",
)
def get_dry_run_state(request: Request) -> dict[str, Any]:
    current = _runner(request).current()
    stopping = current is not None and current.kind == KIND and current.stopping
    session = _session(request)
    with session.lock:
        running = None if session.running is None else _run_out(session.running, stopping)
        last = None if session.last is None else _run_out(session.last, False)
    busy = current.kind if current is not None and current.kind != KIND else None
    return {"running": running, "last": last, "busy": busy}


@router.post(
    "/dry-run/stop",
    status_code=204,
    summary="停止試跑",
    description="評完目前這一筆就不再評，還在排隊的標成沒試跑。",
)
def stop_dry_run(request: Request) -> None:
    _runner(request).stop(KIND)
