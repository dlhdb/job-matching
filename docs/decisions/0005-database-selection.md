# 0005 資料庫選型

## 決策背景與問題

job-database 要把每次抓到的職缺累積到同一個地方（見 [job-database §1](../features/job-database.md#1-背景與目標)），job-scoring 與 mcp-server 之後也會讀寫同一份資料。要決定用哪一種資料庫。

- 專案只有求職者本人在本機使用，不做多使用者服務（見 [非目標](../README.md#非目標)）。
- 目標是快速開發，不想為了存資料另外啟動與管理一套資料庫服務。

## 考慮過的替代方案

- 伺服器型資料庫（例如 PostgreSQL、MySQL）：
  - 要另外安裝、啟動並管理資料庫服務，例如帳號密碼、容器，拖慢開發。
  - 它擅長的多人同時寫入與遠端連線，單人在本機使用時用不到。

## 最終決策

- 採用 SQLite，整個資料庫是單一檔案 `data/jobs.db`。
  - 使用標準函式庫 `sqlite3`，不必安裝或啟動任何服務，也不新增依賴。
  - 可以直接用 `pandas.read_sql` 或任何 SQLite 工具讀取。
  - 一樣是 SQL 資料庫：之後需要改用 PostgreSQL 等 SQL 資料庫時，資料表設計與查詢大多可以沿用，遷移成本低。
- 影響的文件：
  - [architecture.md 的資料存放](../architecture.md#資料存放)
  - [job-database §7.2](../features/job-database.md#72-設計)：模組佈局與資料表
  - [job-scoring 技術設計](../tech-design/job-scoring.md#32-job_scores-資料表)：`job_scores` 表
