# 做出 web app 第 2 階段

為什麼見 [TODO.md](../TODO.md#做出-web-app-第-2-階段)。

- 範圍：職缺表（篩選、排序、點一列展開）、抓取頁（抓取、預覽、存入）、從介面送去評分、設定編輯與試跑。需求見各功能文件：[job-database](../../docs/product/features/job-database.md)、[104-job-scraper](../../docs/product/features/104-job-scraper.md)、[job-auto-scoring](../../docs/product/features/job-auto-scoring.md)，標〔規劃中〕的部分；介面的分工見[決策紀錄：介面形式選型](../../docs/decisions/product/interface-selection.md)。原型在 `prototypes/job-table/`。
- 技術選型：React + TypeScript + Vite 的前端，加上 FastAPI 的後端，見[決策紀錄：web app 框架選型](../../docs/decisions/tech/web-framework-selection.md)
- 實作時要一起移除或修改的程式、測試與技術設計（功能文件已先改好）：
  - job-database：
    - 寫入後在終端機印出的摘要：印在共用的寫入模組裡，和抓取 CLI、匯入 CLI 一起拿掉；職缺資料庫、爬蟲與匯入的測試中檢查摘要的部分，以及技術設計寫入流程中印摘要的那一步跟著改
    - 列出執行紀錄、只列出某一次寫入的職缺、最多取幾筆與從第幾筆開始的查詢：職缺表用不到，執行紀錄的查詢等趨勢分析規劃時再決定去留（見[做趨勢圖表](trend-charts.md)）
    - 技術設計驗收對照中連到已改寫的 AC-query-list、AC-query-get、AC-query-runs 的項目改連到新的 AC，§3.3 的「實現 FR-query-*」也跟著改。以職缺代碼取出單筆職缺的查詢仍給其他模組用，程式與測試保留，只是不再是職缺資料庫對使用者的需求
  - job-auto-scoring（合併 job-score-database）：
    - 評分 CLI（`score_job.py`，含 `--job-no`、`--dry-run`、`--profile-dir`、`--provider`、`--model`、`--db`）：送去評分與試跑的介面完成時拿掉
    - `profile/` 與它的 `.example` 範本、讀個人資料檔的程式：設定改存資料庫後拿掉
    - 試跑結果檔（`output/scores/`）
    - 手動評分的寫入與檢查、`評分來源` 欄，以及評分資料庫「評分的職缺不必先寫進職缺資料庫」的處理（見[補上評分紀錄的遷移](score-history-migration.md)）
    - job-score-database 的技術設計併進 job-auto-scoring 的技術設計；architecture.md 的模組、資料表歸屬與 `profile/` 的資料存放位置跟著改
    - 技術設計與 architecture.md 中連到 job-auto-scoring、job-score-database 功能文件的章節與 AC 連結：錨點斷掉的要改，錨點還在但內容已改成網頁版的 AC（例如 AC-score-store、AC-score-failure、AC-history-current）也要重新對照驗證方式
  - 104-job-scraper：
    - 抓取 CLI（`fetch_104_jobs.py` 的參數、互動模式、Ctrl+C 的處理、`--db`、`--no-db`）與縣市名稱的模糊比對：抓取頁完成時拿掉
    - CSV 與 JSON 輸出檔（`output/104/`）與檔名規則，以及寫入資料庫失敗時因為檔案已寫出而不中斷的處理
    - 匯入 CLI（`import_jobs.py`）與它的測試
    - AC-search-real 改成技術設計「不屬於任何 AC 的檢查」中的整合檢查〔需網路〕，e2e 測試跟著調整
    - 技術設計與 architecture.md 中連到已刪章節與 AC（output、import、CLI、AC-store 等）的連結改掉，驗收對照改成新的 AC
  - README.md：抓取與評分 CLI 的使用說明、輸出檔與匯入 JSON 的說明、複製範本到 `profile/` 的設定步驟，以及專案結構的 `profile/`、`output/`
