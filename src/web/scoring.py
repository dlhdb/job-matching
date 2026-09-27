"""
評分的 API：職缺表上的評分欄位與展開列、送去評分前的確認，以及在背景跑的評分作業。

評分作業照職缺表的顯示順序逐筆評，每筆評完就寫入；進度、每筆的狀態與失敗原因只留在記憶體，
作業結束後保留最近一次的結果，web app 關閉時一起消失。
"""

import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from job_db import current_versions, get_job, get_version, list_current_scores, list_scores, open_db
from job_scoring.batch import score_batch
from job_scoring.llm import DEFAULT_PROVIDER, MODELS, LLMError, api_key_missing, get_client
from job_scoring.models import BatchResult
from job_scoring.prompt import build_prompt
from job_scoring.rules import check_hard_filters
from job_scoring.settings import (
    EXPERIENCE, KIND_NAMES, PREFERENCES, TEMPLATE, ScoringSettings, SettingsError, is_default, load_current,
    parse_preferences,
)
from web.db import connect
from web.jobs import Job, JobBusy, JobRunner

KIND = "評分"


@dataclass
class Run:
    """一次評分作業：將評的職缺、每筆的狀態與各結果的筆數"""

    id: int
    codes: list[str]
    # 還沒評完或評分失敗的職缺：職缺代碼 → (狀態, 失敗原因)；評完的職缺不在其中
    statuses: dict[str, tuple[str, str | None]]
    done: int = 0
    ok: int = 0
    eliminated: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: bool = False
    error: str | None = None


@dataclass
class ScoringSession:
    """評分作業的狀態：在跑的作業與最近一次結束的作業"""

    lock: threading.Lock = field(default_factory=threading.Lock)
    last_id: int = 0
    running: Run | None = None
    last: Run | None = None


# ---------------------------------------------------------------------------
# 請求與回應的模型
# ---------------------------------------------------------------------------

class CurrentScore(BaseModel):
    職缺代碼: str
    評分時間: str
    淘汰: bool
    總分: int | None
    評語: str
    供應商: str | None
    模型: str | None
    維度分數: dict[str, int | None] | None = Field(description="維度名稱 → 1–5 分或 null；被淘汰時為 null")


class ScoreList(BaseModel):
    scores: list[CurrentScore] = Field(description="每筆評過分的職缺一筆代表的評分；沒評過的職缺不在其中")


class DimensionOut(BaseModel):
    分數: int | None
    理由: str


class ScoreDetails(BaseModel):
    職缺代碼: str
    淘汰: bool
    淘汰原因: list[str]
    維度: dict[str, DimensionOut] | None = Field(description="依維度的順序排列；被淘汰時為 null")
    總分: int | None
    未知維度: list[str]
    評語: str


class VersionOut(BaseModel):
    version: int
    name: str
    saved_at: str
    content: str


class PromptOut(BaseModel):
    system: str
    user: str


class Basis(BaseModel):
    preferences: VersionOut
    experience: VersionOut
    template: VersionOut
    snapshot: dict[str, str | int | None] = Field(description="送評時的職缺內容快照")
    prompt: PromptOut | None = Field(description="由快照與三份設定的版本組回的提示詞；被淘汰或組不回來時為 null")
    prompt_error: str | None = Field(description="沒被淘汰卻組不回提示詞的原因")


class ScoreRecord(BaseModel):
    評分時間: str
    淘汰: bool
    總分: int | None
    評語: str
    供應商: str | None
    模型: str | None
    評分明細: ScoreDetails
    basis: Basis | None = Field(description="評分依據；記錄依據之前的評分為 null")


class ScoreHistory(BaseModel):
    records: list[ScoreRecord] = Field(description="依評分時間由新到舊，同一秒內後寫入的在前；沒評過時為空清單")


class PlanRequest(BaseModel):
    codes: list[str] = Field(description="勾選的職缺代碼，依職缺表的顯示順序")
    rescore: bool = Field(description="包含已評過的職缺（重評）")


class StartRequest(PlanRequest):
    model: str


class VersionRef(BaseModel):
    version: int
    name: str


class Plan(BaseModel):
    selected: int = Field(description="勾選幾筆")
    scored: int = Field(description="勾選的職缺中幾筆已評過")
    targets: int = Field(description="將評幾筆")
    eliminated: int | None = Field(description="將評的職缺中幾筆符合淘汰條件；偏好有錯時為 null")
    versions: dict[str, VersionRef] = Field(description="目前設定：preferences、experience、template")
    provider: str
    models: list[str] = Field(description="可以選的模型，第一個是預設")
    errors: list[str] = Field(description="開始前的錯誤；有錯誤時不能送出")


class Started(BaseModel):
    run_id: int


class RowStatus(BaseModel):
    code: str
    status: Literal["queued", "scoring", "failed"]
    reason: str | None = Field(description="評分失敗的原因")


class RunOut(BaseModel):
    id: int
    total: int
    done: int = Field(description="評完幾筆，含失敗")
    ok: int = Field(description="評分成功、沒被淘汰")
    eliminated: int
    failed: int
    skipped: int = Field(description="停止後沒評的筆數")
    stopping: bool
    stopped: bool = Field(description="按了停止，或因為錯誤而停止")
    error: str | None = Field(description="讓評分停止的錯誤")
    statuses: list[RowStatus] = Field(description="還沒評完或評分失敗的職缺，依評分的順序")


class ScoringState(BaseModel):
    running: RunOut | None = Field(description="沒在評分時為 null")
    last: RunOut | None = Field(description="最近一次結束的評分；web app 啟動後還沒評過時為 null")
    busy: str | None = Field(description="正在跑的其他作業，例如「抓取」")


# ---------------------------------------------------------------------------
# 確認與作業
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


def _session(request: Request) -> ScoringSession:
    session: ScoringSession = request.app.state.scoring
    return session


def _runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


@dataclass
class _Checked:
    """開始前的檢查：確認視窗要顯示的內容，以及開始評分要用的設定與職缺"""

    plan: dict[str, Any]
    settings: ScoringSettings | None
    jobs: list[dict[str, Any]]


def _check(conn: sqlite3.Connection, codes: list[str], rescore: bool) -> _Checked:
    """
    依目前設定算出將評哪些職缺，並做開始前的檢查（不含是否有其他作業在跑）

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param codes: list[str], 勾選的職缺代碼，依職缺表的顯示順序
    :param rescore: bool, 是否包含已評過的職缺
    :return: _Checked
    """
    codes = list(dict.fromkeys(codes))
    errors: list[str] = []
    found = {code: job for code in codes if (job := get_job(conn, code)) is not None}
    if len(found) < len(codes):
        errors.append(f"有 {len(codes) - len(found)} 筆勾選的職缺不在職缺資料庫中，請重新整理職缺表")
    scored = {row["職缺代碼"] for row in list_current_scores(conn)}
    jobs = [job for code, job in found.items() if rescore or code not in scored]

    current = current_versions(conn)
    try:
        settings: ScoringSettings | None = load_current(conn)
    except SettingsError as e:
        settings = None
        errors.extend(f"目前設定有錯，先到設定頁修正。{message}" for message in e.messages)

    eliminated = None
    if settings is not None:
        eliminated = sum(1 for job in jobs if check_hard_filters(job, settings.preferences))

    if codes and not jobs and not errors:
        errors.append("將評 0 筆：勾選的職缺都評過了。要重評請勾「包含已評過的職缺（重評）」")
    if not codes:
        errors.append("沒有勾選任何職缺")
    for kind in (PREFERENCES, EXPERIENCE):
        if kind in current and is_default(kind, current[kind]["內容"]):
            errors.append(
                f"目前設定的{KIND_NAMES[kind]}還是預設範例：先到設定頁改成自己的{KIND_NAMES[kind]}，用範例評出的分數沒有意義"
            )
    # 偏好有錯、算不出淘汰筆數時，當作每一筆都要呼叫 AI
    needs_ai = len(jobs) - (eliminated or 0)
    if needs_ai > 0 and api_key_missing(DEFAULT_PROVIDER):
        errors.append(
            f"沒有設定 API key：有 {needs_ai} 筆需要呼叫 AI，請在專案根目錄的 .env 設定 GEMINI_API_KEY（範本見 .env.example）"
        )

    plan = {
        "selected": len(codes),
        "scored": sum(1 for code in found if code in scored),
        "targets": len(jobs),
        "eliminated": eliminated,
        "versions": {kind: {"version": v["版本"], "name": v["名稱"]} for kind, v in current.items()},
        "provider": DEFAULT_PROVIDER,
        "models": MODELS[DEFAULT_PROVIDER],
        "errors": errors,
    }
    return _Checked(plan=plan, settings=settings, jobs=jobs)


def _run_out(run: Run, stopping: bool) -> dict[str, Any]:
    return {
        "id": run.id,
        "total": len(run.codes),
        "done": run.done,
        "ok": run.ok,
        "eliminated": run.eliminated,
        "failed": run.failed,
        "skipped": run.skipped,
        "stopping": stopping,
        "stopped": run.stopped,
        "error": run.error,
        "statuses": [
            {"code": code, "status": status, "reason": reason}
            for code in run.codes
            if (entry := run.statuses.get(code)) is not None
            for status, reason in [entry]
        ],
    }


def _score(
    session: ScoringSession, run: Run, db_path: Path, jobs: list[dict[str, Any]], settings: ScoringSettings, model: str,
) -> Any:
    """
    產生評分作業的 target：照順序逐筆評，結束時把這次的結果交給 session

    :return: callable, target(job)
    """

    def on_start(_: int, job: dict[str, Any]) -> None:
        with session.lock:
            run.statuses[job["職缺代碼"]] = ("scoring", None)

    def on_result(_: int, result: BatchResult) -> None:
        with session.lock:
            run.done += 1
            if result.failure is not None:
                run.failed += 1
                run.statuses[result.job_no] = ("failed", result.failure)
                return
            if result.eliminated:
                run.eliminated += 1
            else:
                run.ok += 1
            del run.statuses[result.job_no]

    def fail_current(reason: str, error: str) -> None:
        """讓評分停止的錯誤：正在評的那一筆算失敗，並記下錯誤"""
        with session.lock:
            for code, (status, _) in run.statuses.items():
                if status == "scoring":
                    run.statuses[code] = ("failed", reason)
                    run.done += 1
                    run.failed += 1
            run.error = error

    def target(job: Job) -> None:
        try:
            with closing(open_db(db_path)) as conn:
                score_batch(
                    jobs, settings, lambda: get_client(DEFAULT_PROVIDER, model),
                    conn=conn, provider=DEFAULT_PROVIDER, model=model,
                    should_stop=job.stop.is_set, on_start=on_start, on_result=on_result,
                )
        except LLMError as e:
            with session.lock:
                run.error = f"無法開始評分：{e}"
        except sqlite3.Error as e:
            # 寫入失敗的那一筆算失敗；之後的不再評
            fail_current(f"寫入資料庫失敗：{e}", f"無法寫入資料庫，已停止：{e}")
        except Exception as e:
            fail_current(f"評分中發生錯誤：{e}", f"評分中發生錯誤，已停止：{e}")
            raise
        finally:
            with session.lock:
                queued = [code for code, (status, _) in run.statuses.items() if status in ("queued", "scoring")]
                for code in queued:
                    del run.statuses[code]
                run.skipped = len(queued)
                run.stopped = job.stopping or run.error is not None
                session.running = None
                session.last = run

    return target


# ---------------------------------------------------------------------------
# 端點
# ---------------------------------------------------------------------------

@router.get(
    "/scores",
    response_model=ScoreList,
    summary="列出各職缺代表的評分",
    description="每筆評過分的職缺只列一筆：評分時間最新的一筆，同一秒內後寫入的；職缺表的評分欄位、排序與篩選都用它。",
)
def get_scores(request: Request) -> dict[str, Any]:
    with connect(request) as conn:
        rows = list_current_scores(conn)
    scores = []
    for row in rows:
        dimensions = row.pop("評分明細")["維度"]
        row["維度分數"] = None if dimensions is None else {name: d["分數"] for name, d in dimensions.items()}
        scores.append(row)
    return {"scores": scores}


def _basis(conn: sqlite3.Connection, record: dict[str, Any]) -> dict[str, Any] | None:
    """
    組出評分依據：三份設定的版本內容、職缺快照，以及組回的提示詞

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :param record: dict, list_scores 回傳的一筆評分紀錄
    :return: dict or None, Basis；記錄依據之前的評分為 None
    """
    if record["職缺快照"] is None:
        return None
    versions: dict[str, dict[str, Any]] = {}
    for kind, column in ((PREFERENCES, "偏好版本"), (EXPERIENCE, "經歷版本"), (TEMPLATE, "模板版本")):
        # 設定的版本只新增不刪除，紀錄指向的版本一定存在
        version = get_version(conn, kind, record[column])
        assert version is not None
        versions[kind] = version

    prompt = prompt_error = None
    if not record["淘汰"]:
        try:
            prefs = parse_preferences(versions[PREFERENCES]["內容"])
            system, user = build_prompt(
                record["職缺快照"], prefs, versions[EXPERIENCE]["內容"], versions[TEMPLATE]["內容"],
            )
            prompt = {"system": system, "user": user}
        except (SettingsError, ValueError) as e:
            prompt_error = f"這一版的設定不符合現在的規則，組不回提示詞：{e}"

    return {
        **{
            kind: {"version": v["版本"], "name": v["名稱"], "saved_at": v["儲存時間"], "content": v["內容"]}
            for kind, v in versions.items()
        },
        "snapshot": record["職缺快照"],
        "prompt": prompt,
        "prompt_error": prompt_error,
    }


@router.get(
    "/scores/{job_no}",
    response_model=ScoreHistory,
    summary="取出一筆職缺的所有評分紀錄",
    description="展開列用：每筆含評分明細與評分依據，依據中的提示詞由送評時的職缺快照與當時的設定版本組回。",
)
def get_score_history(request: Request, job_no: str) -> dict[str, Any]:
    with connect(request) as conn:
        records = list_scores(conn, job_no)
        return {"records": [{**record, "basis": _basis(conn, record)} for record in records]}


@router.post(
    "/scoring/plan",
    response_model=Plan,
    summary="送去評分前的確認",
    description="確認視窗用：將評幾筆、其中幾筆淘汰、用哪一版設定，以及開始前的錯誤。",
)
def plan_scoring(request: Request, body: PlanRequest) -> dict[str, Any]:
    with connect(request) as conn:
        plan = _check(conn, body.codes, body.rescore).plan
    running = _runner(request).current()
    if running is not None:
        plan["errors"].append(str(JobBusy(running.kind)))
    return plan


@router.post(
    "/scoring",
    status_code=202,
    response_model=Started,
    summary="開始評分",
    description=(
        "重讀目前設定並重做開始前的檢查，有錯時回 422（detail 是錯誤清單）；已有作業在跑時回 409。"
        "通過後在背景照 codes 的順序逐筆評，進度以 GET /api/scoring 取得。"
    ),
)
def start_scoring(request: Request, body: StartRequest) -> dict[str, Any]:
    if body.model not in MODELS[DEFAULT_PROVIDER]:
        raise HTTPException(status_code=422, detail=[f"不認得的模型：{body.model}"])
    runner, session = _runner(request), _session(request)
    with connect(request) as conn:
        checked = _check(conn, body.codes, body.rescore)
    if checked.plan["errors"]:
        raise HTTPException(status_code=422, detail=checked.plan["errors"])
    assert checked.settings is not None

    codes = [job["職缺代碼"] for job in checked.jobs]
    with session.lock:
        run = Run(id=session.last_id + 1, codes=codes, statuses={code: ("queued", None) for code in codes})
        try:
            # 作業的執行緒要拿到 session.lock 才能更新狀態，所以一定在下面設定 running 之後
            runner.start(KIND, _score(session, run, request.app.state.db_path, checked.jobs, checked.settings, body.model))
        except JobBusy as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        session.last_id = run.id
        session.running = run
    return {"run_id": run.id}


@router.get(
    "/scoring",
    response_model=ScoringState,
    summary="取得評分作業的狀態",
    description="評分中的進度與每筆的狀態、最近一次結束的評分，以及正在跑的其他作業。",
)
def get_scoring_state(request: Request) -> dict[str, Any]:
    current = _runner(request).current()
    stopping = current is not None and current.kind == KIND and current.stopping
    session = _session(request)
    with session.lock:
        running = None if session.running is None else _run_out(session.running, stopping)
        last = None if session.last is None else _run_out(session.last, False)
    busy = current.kind if current is not None and current.kind != KIND else None
    return {"running": running, "last": last, "busy": busy}


@router.post(
    "/scoring/stop",
    status_code=204,
    summary="停止評分",
    description="評完目前這一筆就不再評，還在排隊的不評；已評完的留在資料庫。",
)
def stop_scoring(request: Request) -> None:
    _runner(request).stop(KIND)
