"""
啟動求職雷達的網頁：uv run src/app.py，再用瀏覽器打開 http://127.0.0.1:8000。
"""

import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from job_db import DEFAULT_DB_PATH
from web import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    """
    載入 .env，以 uvicorn 啟動 API 與 build 好的前端

    沒有前端的 build 時照樣啟動 API：開發時由 Vite 的開發伺服器提供前端。
    """
    load_dotenv(PROJECT_ROOT / ".env")
    frontend_dir: Path | None = FRONTEND_DIST
    if not (FRONTEND_DIST / "index.html").is_file():
        print("[!] 找不到前端的 build，先在 frontend/ 執行 npm run build；這次只提供 API", file=sys.stderr)
        frontend_dir = None
    print(f"[i] 在瀏覽器打開 http://{HOST}:{PORT}", file=sys.stderr)
    uvicorn.run(create_app(DEFAULT_DB_PATH, frontend_dir), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
