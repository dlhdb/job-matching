# 做出 web app 第 2 階段

為什麼見 [TODO.md](../TODO.md#做出-web-app-第-2-階段)。

- 範圍：職缺表（篩選、排序、點一列展開）、抓取頁（抓取、預覽、存入）、從介面送去評分、設定編輯與試跑。需求見各功能文件：[job-database](../../docs/product/features/job-database.md)、[104-job-scraper](../../docs/product/features/104-job-scraper.md)、[job-auto-scoring](../../docs/product/features/job-auto-scoring.md)，標〔規劃中〕的部分；介面的分工見[決策紀錄：介面形式選型](../../docs/decisions/product/interface-selection.md)。原型在 `prototypes/job-table/`。
- 技術選型：React + TypeScript + Vite 的前端，加上 FastAPI 的後端，見[決策紀錄：web app 框架選型](../../docs/decisions/tech/web-framework-selection.md)
- 實作時要一起移除或修改的程式、測試與技術設計（功能文件已先改好）：
  - job-database：
    - 列出執行紀錄的查詢：職缺表用不到，等趨勢分析規劃時再決定去留（見[做趨勢圖表](trend-charts.md)）
  - job-auto-scoring（合併 job-score-database）：
    - 評分 CLI（`score_job.py`，含 `--job-no`、`--dry-run`、`--profile-dir`、`--provider`、`--model`、`--db`）：送去評分與試跑的介面完成時拿掉
    - `profile/` 與它的 `.example` 範本、讀個人資料檔的程式：設定改存資料庫後拿掉
    - 試跑結果檔（`output/scores/`）
    - 手動評分的寫入與檢查、`評分來源` 欄，以及評分資料庫「評分的職缺不必先寫進職缺資料庫」的處理（見[補上評分紀錄的遷移](score-history-migration.md)）
    - job-score-database 的技術設計併進 job-auto-scoring 的技術設計；architecture.md 的模組、資料表歸屬與 `profile/` 的資料存放位置跟著改
    - 技術設計與 architecture.md 中連到 job-auto-scoring、job-score-database 功能文件的章節與 AC 連結：錨點斷掉的要改，錨點還在但內容已改成網頁版的 AC（例如 AC-score-store、AC-score-failure、AC-history-current）也要重新對照驗證方式
  - README.md：評分 CLI 的使用說明、複製範本到 `profile/` 的設定步驟，以及專案結構的 `profile/`、`output/`
