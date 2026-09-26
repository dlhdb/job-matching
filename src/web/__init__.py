"""
求職雷達的網頁後端：組裝各功能的 API（/api/...），並提供 build 好的前端。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from job_db import open_db
from web import crawl, job_table
from web.jobs import JobRunner


def create_app(db_path: str | Path, frontend_dir: Path | None = None) -> FastAPI:
    """
    建立 FastAPI app。

    :param db_path: str or Path, 職缺資料庫的路徑；每個請求與背景作業各自開自己的連線
    :param frontend_dir: Path or None, build 好的前端目錄（含 index.html 與 assets/）；None 時只提供 API
    :return: FastAPI
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # 啟動時先開一次，資料庫的錯誤在啟動時就出現，不等到第一個請求
        open_db(db_path).close()
        yield

    app = FastAPI(title="求職雷達", lifespan=lifespan)
    app.state.db_path = Path(db_path)
    # 同一時間只跑一個作業，各功能共用同一個執行器
    app.state.runner = JobRunner()
    app.state.crawl = crawl.CrawlSession()
    app.include_router(job_table.router)
    app.include_router(crawl.router)

    if frontend_dir is not None:
        _serve_frontend(app, frontend_dir)
    return app


def _serve_frontend(app: FastAPI, frontend_dir: Path) -> None:
    """
    提供 build 好的前端：/assets 回靜態檔，其他不是 /api 的路徑一律回 index.html

    前端以 react-router 切換頁面，/crawl、/settings 重新整理時也要拿到 index.html 才打得開。

    :param app: FastAPI, 已掛上各功能 API 的 app
    :param frontend_dir: Path, build 好的前端目錄
    """
    app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")
    index = frontend_dir / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        # 每次 build 會換掉 assets 的檔名並刪除舊檔，瀏覽器留著舊的 index.html 會載入不存在的 JS
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
