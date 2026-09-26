# 做出 web app 第 2 階段

為什麼見 [TODO.md](../TODO.md#做出-web-app-第-2-階段)。

- 範圍：職缺表（篩選、排序、點一列展開）、抓取頁（抓取、預覽、存入）、從介面送去評分、設定編輯與試跑。需求見各功能文件：[job-database](../../docs/product/features/job-database.md)、[104-job-scraper](../../docs/product/features/104-job-scraper.md)、[job-auto-scoring](../../docs/product/features/job-auto-scoring.md)，標〔規劃中〕的部分；介面的分工見[決策紀錄：介面形式選型](../../docs/decisions/product/interface-selection.md)。原型在 `prototypes/job-table/`。
- 技術選型：React + TypeScript + Vite 的前端，加上 FastAPI 的後端，見[決策紀錄：web app 框架選型](../../docs/decisions/tech/web-framework-selection.md)
- 實作時要一起移除或修改的程式、測試與技術設計（功能文件已先改好）：
  - job-database：
    - 列出執行紀錄的查詢：職缺表用不到，等趨勢分析規劃時再決定去留（見[做趨勢圖表](trend-charts.md)）
  - job-auto-scoring：
    - 試跑結果檔（`output/scores/`）與寫出它的 `batch.write_dry_run_results`：試跑的介面完成時拿掉
    - 技術設計的驗收對照：操作改成網頁版的 AC（例如 AC-score-store、AC-rescore-failure、AC-history-append）目前以整批評分的測試暫代，送去評分的介面完成時改成網頁的驗證方式
  - README.md：送去評分與試跑的使用說明
