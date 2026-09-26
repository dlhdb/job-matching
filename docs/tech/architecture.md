# 系統架構

本文件是跨功能的技術總覽：模組之間怎麼依賴、資料放在哪裡、用了哪些技術。

- 功能之間的資料流見 [專案總覽的使用者旅程](../product/overview.md#使用者旅程)。
- 各模組的細節見對應的技術設計，本文件只列總覽並連過去。

## 執行方式

- 在本機手動執行，不排程（見 [非目標](../product/overview.md#非目標)）。
- 每個進入點都是 `src/` 下的一支腳本，以 `uv run src/<腳本>.py` 執行：
  - `app.py`：網頁，以 uvicorn 在 `127.0.0.1:8000` 提供 API 與 build 好的前端，只接受本機連線
    - 啟動前先把舊版的資料庫改成最新版（見 [job-database 的資料庫改版](tech-design/job-database.md#34-資料庫改版)）
    - 前端在 `frontend/`，要先 build 才能從這裡打開
    - 開發時改用 Vite 的開發伺服器，它把 `/api` 轉給 `app.py`
    - 目前有職缺表（見 [job-database 的職缺表](tech-design/job-database.md#22-職缺表的前後端分工)）、抓取頁（見 [104-job-scraper 的流程](tech-design/104-job-scraper.md#2-流程)）與設定頁（見 [job-auto-scoring 的設定頁](tech-design/job-auto-scoring.md#24-設定頁)）
    - 還沒有評分的入口：評分的程式已在 `job_scoring`，在職缺表送去評分的介面還沒做

## 模組依賴

```mermaid
flowchart LR
    frontend["frontend/"] -->|"/api"| web["web"]
    app["app.py"] --> web
    app --> jobdb
    web --> jobdb["job_db"]
    web --> fetch["fetch_104_jobs.py"]
    web --> scoring["job_scoring"]
    scoring --> jobdb
    jobdb --> db[("data/jobs.db")]
    fetch --> api104(["104 API"])
    scoring --> gemini(["Gemini API"])
```

- `job_db` 在最底層，不 import 專案內的其他模組。原因見 [job-database 的技術設計總覽](tech-design/job-database.md#1-總覽)。
- `web`：網頁的後端，組裝各功能的 API（都在 `/api` 下），並提供 build 好的前端。
  - 各功能的 API 各自一個模組，由擁有該資料的功能負責，例如職缺表的 `web/job_table.py` 屬於 job-database，抓取頁的 `web/crawl.py` 屬於 104-job-scraper，設定頁的 `web/settings.py` 屬於 job-auto-scoring。
  - `web/jobs.py` 是各功能共用的作業執行器：
    - 抓取這類要跑一段時間的工作在背景執行緒跑。
    - 同一時間只跑一個。
    - 重新整理或關掉頁面都不影響。
  - 每個請求各自開一條資料庫連線，用完就關：同步的端點跑在 threadpool，`sqlite3` 的連線不能跨執行緒使用。
  - 啟動時先開一次資料庫，資料庫的錯誤在啟動時就出現。
    - 同時替還沒有設定的資料庫寫入評分設定的第 1 版。
  - 不是 `/api` 開頭的路徑一律回前端的 `index.html`，前端以 react-router 切換頁面，重新整理 `/crawl` 這類路徑時才打得開。
- `fetch_104_jobs.py`：向 104 抓取職缺（見 [104-job-scraper 的技術設計總覽](tech-design/104-job-scraper.md#1-總覽)）。
  - 不 import `job_db`。
  - 抓到的職缺交給 `web/crawl.py` 預覽與存入。
- `frontend/`：網頁的前端。
  - 各功能的頁面各自一個目錄，例如 `frontend/src/job-database/`、`frontend/src/crawl/`、`frontend/src/settings/`。
  - 外殼與導覽在 `frontend/src/app/`。
- `job_scoring`：評分與評分用的設定（見 [job-auto-scoring 的技術設計總覽](tech-design/job-auto-scoring.md#1-總覽)）。
  - 經由 `job_db/scores.py` 寫入 `job_scores`，經由 `job_db/settings.py` 讀寫設定的版本。
  - 這兩個模組放在 `job_db` 套件，但屬於 job-auto-scoring。

## 資料存放

`data/jobs.db`：所有功能共用的 SQLite 資料庫，不進版控。選用 SQLite 的理由見 [決策紀錄：資料庫選型](../decisions/tech/database-selection.md)。

- 所有表的建表語法都放在 `job_db` 的 schema，開啟資料庫時一起建立。
- 結構的版本記在 `PRAGMA user_version`，改版前先備份到同一個目錄（見 [資料庫改版](tech-design/job-database.md#34-資料庫改版)）。
- 各表由哪個功能負責：
  - `jobs`、`scrape_runs`、`run_jobs`：job-database（見 [資料表](tech-design/job-database.md#32-資料表)）
    - 寫入：104-job-scraper 的抓取頁，預覽後存入（見 [抓取頁的流程](tech-design/104-job-scraper.md#2-流程)）
  - `job_scores`：job-auto-scoring（見 [job_scores](tech-design/job-auto-scoring.md#32-job_scores)）
    - 同一筆職缺可以有多列，記下評分依據
    - 寫入：整批評分，目前還沒有呼叫端
  - `settings_versions`、`current_settings`：job-auto-scoring（見 [設定的版本](tech-design/job-auto-scoring.md#31-設定的版本)）
    - 寫入：設定頁
- 表之間以 `職缺代碼` 關聯，它是 `jobs` 的主鍵。
- `job_scores` 以 `評分編號` 為主鍵，`職缺代碼` 以外鍵指向 `jobs`，同一個 `職缺代碼` 可以有多列。
- 欄名沿用中文，與[職缺欄位契約](../product/features/job-database.md#821-職缺欄位契約)、評分結果的鍵名一致。

檔案：

- `output/e2e/`：e2e 測試留下供查看的檔案，例如評分測試的資料庫 `jobs.db`，不進版控（見 [測試](../conventions/development.md#測試)）
- `data/jobs.db.v<版本>-<時間>.bak`：資料庫改版前的備份，不進版控，確認資料沒問題後由使用者自己刪
- `src/job_scoring/defaults/`：評分設定的預設內容（偏好、經歷、提示詞模板），進版控
  - 使用者的設定只存在資料庫
- `.env`：API key，不進版控，範本是 `.env.example`

## 技術選型

- 語言與套件管理：Python 3.14，依賴由 uv 管理（見 [依賴管理](../conventions/development.md#依賴管理)）
- 資料庫：SQLite，使用標準函式庫 `sqlite3`（見 [決策紀錄：資料庫選型](../decisions/tech/database-selection.md)）
- 抓取：`requests` 呼叫 104 的內部 API（見 [104 API 的限制](tech-design/104-job-scraper.md#4-外部系統整合)）
- LLM：Gemini，使用 `google-genai`
  - 經由 `LLMClient` 抽象層呼叫，換供應商不必改其他模組（見 [LLM 供應商抽象層](tech-design/job-auto-scoring.md#41-llm-供應商抽象層)）
- 資料驗證：Pydantic，驗證偏好、AI 輸出與評分結果
- 設定的格式：偏好用 YAML（`pyyaml`），API key 用 `.env`（`python-dotenv`）
- 網頁：後端 FastAPI（以 uvicorn 執行），前端 React + TypeScript，以 Vite build（見 [決策紀錄：web app 框架選型](../decisions/tech/web-framework-selection.md)）
  - 前後端的 API 型別以 `openapi-typescript` 從 FastAPI 的 OpenAPI 產生（見 [API 型別](../conventions/development.md#api-型別)）
  - 頁面切換用 `react-router-dom`
- 測試：pytest
  - 前端的規則用 Vitest
  - 瀏覽器行為用 Playwright（`pytest-playwright`），使用容器內的 Chromium（見 [瀏覽器測試](../conventions/development.md#瀏覽器測試)）
- 前端的 lint 與格式：ESLint、Prettier（見 [前端的 lint 與格式](../conventions/development.md#前端的-lint-與格式)）
