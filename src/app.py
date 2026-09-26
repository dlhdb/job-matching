"""
啟動求職雷達的網頁：uv run src/app.py，再用瀏覽器打開 http://127.0.0.1:8000。
"""

import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from job_db import DEFAULT_DB_PATH, UpgradeError, UpgradeResult, upgrade_db
from web import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
HOST = "127.0.0.1"
PORT = 8000


def report_upgrade(result: UpgradeResult) -> None:
    """
    把資料庫改版的結果印到 stderr

    :param result: UpgradeResult, 改版的結果
    """
    print(f"[+] 資料庫已從第 {result.from_version} 版改成第 {result.to_version} 版，搬移 {result.scores_moved} 筆評分紀錄",
          file=sys.stderr)
    if result.skipped_manual:
        print(f"[!] 略過 {result.skipped_manual} 筆手動評分：新版不再保存手動評分", file=sys.stderr)
    if result.skipped_orphan:
        print(f"[!] 略過 {result.skipped_orphan} 筆評分：職缺資料庫裡沒有對應的職缺", file=sys.stderr)
    print(f"[i] 改版前的備份：{result.backup}（確認資料沒問題後可以自己刪除）", file=sys.stderr)


def main(db_path: Path = DEFAULT_DB_PATH) -> int:
    """
    載入 .env，把舊版的資料庫改成最新版，再以 uvicorn 啟動 API 與 build 好的前端

    沒有前端的 build 時照樣啟動 API：開發時由 Vite 的開發伺服器提供前端。

    :param db_path: Path, 職缺資料庫的路徑
    :return: int, 結束碼；資料庫改版失敗時為 1
    """
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        result = upgrade_db(db_path)
    except UpgradeError as e:
        print(f"[-] 資料庫改版失敗，資料庫維持改版前的內容：{e}", file=sys.stderr)
        return 1
    if result is not None:
        report_upgrade(result)
    frontend_dir: Path | None = FRONTEND_DIST
    if not (FRONTEND_DIST / "index.html").is_file():
        print("[!] 找不到前端的 build，先在 frontend/ 執行 npm run build；這次只提供 API", file=sys.stderr)
        frontend_dir = None
    print(f"[i] 在瀏覽器打開 http://{HOST}:{PORT}", file=sys.stderr)
    uvicorn.run(create_app(db_path, frontend_dir), host=HOST, port=PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
