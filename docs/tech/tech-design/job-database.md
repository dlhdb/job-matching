# 職缺資料庫：技術設計

- 功能文件：[job-database.md](../../product/features/job-database.md)
- 程式碼：
  - 資料庫：[src/job_db/](../../../src/job_db/)
  - 職缺表的 API：[src/web/job_table.py](../../../src/web/job_table.py)
  - 職缺表的頁面：[frontend/src/job-database/](../../../frontend/src/job-database/)

## 1. 總覽

```mermaid
flowchart LR
    page["frontend/src/job-database/"] -->|"GET /api/jobs"| api["web/job_table.py"]
    api --> queries["job_db/queries.py"]
    src["來源功能的進入點"] --> store["job_db/store.py"]
    src --> schema["job_db/schema.py"]
    store --> db[("data/jobs.db")]
    schema --> db
    queries --> db
    queries --> sql["job_db/_sql.py"]
```

模組職責：

- `job_db/schema.py`：所有資料表的建表語法，以及開啟資料庫並建立缺少的表。其他功能的表也在這裡建立，見各功能的技術設計。
- `job_db/store.py`：寫入一批職缺與該次的執行紀錄。
- `job_db/queries.py`：查出職缺與執行紀錄。
- `job_db/_sql.py`：查詢共用的 SQL 組裝（欄名轉 dict、`LIMIT`／`OFFSET`），與哪一張表無關，其他功能放在 `job_db` 的查詢模組也可以共用。
- `web/job_table.py`：職缺表的 API，一次回傳全部職缺。
- `frontend/src/job-database/`：職缺表的頁面，篩選、排序、選欄位、展開、記住檢視與只看剛存入的職缺都在這裡處理。
- `job_db` 的呼叫者是各來源功能的進入點與職缺表的 API，見 [architecture.md 的模組依賴](../architecture.md#模組依賴)。

依賴限制：

- `job_db` 在最底層，不 import 專案內的其他模組。
  - 原因：來源功能會 import `job_db`，反向 import 會形成循環。
  - `schema.py` 的 `JOB_COLUMNS` 是[職缺欄位契約](../../product/features/job-database.md#821-職缺欄位契約)的實作：
    - 來源功能整理出來的欄位（例如爬蟲）對齊它。
    - 是否一致由來源功能的測試檢查（見 [104-job-scraper 技術設計](104-job-scraper.md#6-驗收對照)）。
  - 其他模組呼叫 `job_db` 時，參數都用基本型別。
- 使用標準函式庫 `sqlite3`，不新增依賴（選用 SQLite 的理由見 [決策紀錄：資料庫選型](../../decisions/tech/database-selection.md)）。
- 以 `uv run src/<腳本>.py` 執行時，`src/` 在 import 路徑上，來源功能不需要額外設定就能 import `job_db`。

## 2. 流程

### 2.1 寫入一批職缺

實現 FR-save-*。業務規則見[功能文件的寫入規則](../../product/features/job-database.md#421-寫入規則)。

`store.save_run` 是所有來源共用的寫入進入點，整批在同一個 transaction 中：

1. 在 `scrape_runs` 新增一列，`職缺數` 先填 0。
2. 逐筆寫入 `jobs`：
   - 先查出既有列的首次與最後出現時間，依規則新增或更新。
   - 更新時，`工作內容`、`薪資待遇` 以 `COALESCE(新值, 舊值)` 寫入，其他欄位直接覆蓋。
3. 逐筆以 `INSERT OR IGNORE` 寫入 `run_jobs`，同一次寫入中重複的職缺代碼只留一列。
4. 以不重複的職缺代碼數回填 `scrape_runs.職缺數`。

- 新增與更新的筆數以回傳值交給呼叫端，`job_db` 不印任何訊息。
- 任何一步拋出例外，整個 transaction rollback，三張表都不變。呼叫端怎麼回報錯誤由來源功能決定（例如 [104-job-scraper 技術設計](104-job-scraper.md#5-錯誤處理)）。

### 2.2 職缺表的前後端分工

實現 FR-query-*、FR-just-saved-*。規則見功能文件的[職缺表](../../product/features/job-database.md#5-在職缺表瀏覽篩選累積下來的職缺query)與[只看剛存入的職缺](../../product/features/job-database.md#6-只看剛存入的職缺just-saved)。

後端只負責把資料交出去：

- `GET /api/jobs` 一次回傳全部職缺，排序同 `list_jobs`，不分頁、不篩選。
- 回應模型從 `JOB_COLUMNS` 產生，[職缺欄位契約](../../product/features/job-database.md#821-職缺欄位契約)只寫在一處。
  - 除了 `職缺代碼` 與兩個出現時間，其他欄位都允許 `null`：資料表沒有 `NOT NULL`，模型不能比資料表嚴格。
- 前端的型別從這個模型產生（見 [development.md 的 API 型別](../../conventions/development.md#api-型別)）。

看資料的方式都在前端：

- 篩選、排序、選欄位、展開、記住的檢視與只看剛存入的職缺，只影響畫面，不改資料。
- 全部職缺載入一次，之後在瀏覽器篩選、排序，不必每次改條件都呼叫 API。
  - 資料量在上千筆以內，不需要分頁或虛擬捲動。
- 規則寫成純函式（欄位、排序、篩選、檢視、剛存入），用 Vitest 測；元件只負責畫面。
- 表格元件不綁定資料：要列的職缺、欄位定義、展開的內容與每列的標記都由呼叫端傳入。
- 不用表格函式庫：排序規則是自訂的（沒有值的排最後、最後以職缺代碼排序），寫成純函式比設定函式庫直接。

前後端要一致的地方：

- 排序的最後一個鍵都是 `職缺代碼`，前端逐字元比較，和 SQLite 的預設比較方式相同，預設排序在前後端排出來的順序才一致。

記住的檢視：

- 存在 `localStorage` 的 `jobDatabase.view.v1`，內容是欄位、排序與篩選。
- 讀取時逐項檢查，不合法的項目退回預設，其他項目照用：記錄可能來自舊版，不應讓職缺表打不開。
- 結構改變時換鍵名的版本號，舊的記錄就不會被誤讀。

只看剛存入的職缺：

- 存入職缺的一方以 `/?saved=代碼,代碼` 打開職缺表，這是兩者之間的約定。
- 不另外做「依代碼取出」的 API：全部職缺已經載入，直接從中挑出，N 是挑到的筆數。
- 只看網址，不寫進記住的檢視。
- 關掉標籤時以取代的方式拿掉網址上的參數，重新整理後才不會又套用一次。

## 3. 資料與儲存

實現 FR-db、FR-save-run。每個欄位的業務意義見[功能文件的保存的資訊](../../product/features/job-database.md#822-保存的資訊)。

### 3.1 開啟資料庫

- 預設路徑 `DEFAULT_DB_PATH` 以模組位置推算專案根目錄的 `data/jobs.db`，`data/` 已列入 `.gitignore`。
- `open_db` 自動建立上層目錄，並以 `CREATE TABLE IF NOT EXISTS` 建立所有表。
  - 在既有的資料庫上執行時，只補上缺少的表，不影響原有資料。
- `PRAGMA foreign_keys = ON` 在 transaction 中設定不會生效，所以先以 autocommit 模式開啟連線、設定好之後，才切換成手動 transaction。

### 3.2 資料表

`jobs`：每筆職缺一列。

- [職缺欄位契約](../../product/features/job-database.md#821-職缺欄位契約)的全部欄位：
  - 欄名、順序與契約相同
  - `職缺代碼` 是主鍵
  - 型態依契約轉換：str → `TEXT`，int → `INTEGER`
- `首次出現時間`（TEXT NOT NULL）
- `最後出現時間`（TEXT NOT NULL）

`scrape_runs`：每次寫入一列。

- `執行編號`（INTEGER）：主鍵，`AUTOINCREMENT`
- `執行時間`（TEXT NOT NULL）
- `來源`（TEXT NOT NULL）
- `關鍵字`（TEXT）
- `地區`（TEXT）
- `職缺性質`（INTEGER）
- `頁數`（INTEGER）
- `來源檔`（TEXT UNIQUE）：舊的匯入紀錄匯入的 JSON 檔名，當時用來判斷是否已匯入過
  - 匯入已拿掉，目前沒有寫入這一欄的來源，新的紀錄都是 `NULL`
  - SQLite 的 UNIQUE 允許多個 `NULL`
- `職缺數`（INTEGER NOT NULL）

`關鍵字`、`地區`、`職缺性質`、`頁數` 是來源功能提供的寫入條件（見 [job-database §8.2.2](../../product/features/job-database.md#822-保存的資訊)），目前的欄位是唯一的來源 104-job-scraper 留下的形狀。接第二個求職平台時要重新設計（見 [TODO.md](../../../backlog/TODO.md#把職缺欄位契約改成平台中立)）。

`run_jobs`：一次寫入與其中出現的職缺。

- 主鍵是（`執行編號`, `職缺代碼`）。
- 兩欄分別以外鍵指向 `scrape_runs` 與 `jobs`。

設計理由：

- 欄名沿用中文，讓 `pandas.read_sql` 讀出來的欄位與職缺欄位契約一致，下游不需要做欄名對照。
- 時間存成 ISO 8601 字串，字串比較的結果與時間先後相同，寫入規則可以直接比較。

### 3.3 查詢

`queries.py` 提供職缺與執行紀錄的查詢。職缺與執行紀錄回傳以中文欄名為鍵的 `dict`，鍵就是[職缺欄位契約](../../product/features/job-database.md#821-職缺欄位契約)的欄名，呼叫端不必做欄名對照：

- `list_jobs`：列出全部職缺，職缺表的 API 用它（見 [2.2](#22-職缺表的前後端分工)）。
- `get_job`：以職缺代碼取單筆，查不到時回傳 `None`，不回傳空 `dict`。評分 CLI 用它取出指定的職缺。
- `existing_job_codes`：從一批職缺代碼中找出資料庫已有的，抓取的預覽用它標出新職缺。
  - 代碼以一個 JSON 陣列帶入，不受 SQLite 單一語句參數個數的上限影響。
- `list_runs`：列出執行紀錄。目前沒有使用者需求用到它，留給之後的趨勢分析。

排序都加上主鍵當最後一個排序鍵（職缺是 `最後出現時間` 後接 `職缺代碼`），同樣的資料每次查出來的順序才一致。

查詢介面沒有涵蓋的臨時查詢，仍然直接下 SQL：

- 終端機：`sqlite3 data/jobs.db`（開發容器已安裝，見 [devcontainer.md](../ai-coding-setup/devcontainer.md#容器內的工具)）
- 程式或 notebook：`pandas.read_sql`，中文欄名讀出來就與職缺欄位契約一致

## 4. 驗收對照

測試資料：

- `job_db` 的測試在 `tests/test_job_db.py`。
- 職缺表 API 的測試在 `tests/test_web_job_table.py`。
- 職缺表的規則以 Vitest 測，測試檔在 `frontend/src/` 裡、與原始碼放在一起。
- 職缺表的瀏覽器行為以 Playwright 測，在 `tests/test_browser_job_table.py`。
  - 測試開始前會自動 build 前端（見 [development.md 的瀏覽器測試](../../conventions/development.md#瀏覽器測試)）。
- 資料庫建在 `tmp_path`，職缺資料寫在測試碼裡。

一次跑完所有離線驗收：

```bash
uv run pytest tests/test_job_db.py tests/test_web_job_table.py tests/test_browser_job_table.py
npm test --prefix frontend
```

其他檢查：

- 型別檢查：`uv run mypy src/` 與 `npm run typecheck --prefix frontend`，通過條件為沒有錯誤。
- 前端的 API 型別是否最新：`uv run pytest tests/test_web_openapi.py`。

### save

- [AC-save-dedup](../../product/features/job-database.md#ac-save-dedup跨次去重與出現時間)：`uv run pytest tests/test_job_db.py -k save_run`
- [AC-save-keep-detail](../../product/features/job-database.md#ac-save-keep-detailnull-不覆蓋既有內容)：`uv run pytest tests/test_job_db.py -k keeps_detail`
- [AC-save-run](../../product/features/job-database.md#ac-save-run執行紀錄與整批寫入)：`uv run pytest tests/test_job_db.py -k "save_run and (records or rollback)"`

### query

- [AC-query-list](../../product/features/job-database.md#ac-query-list一次列出全部符合的職缺)：`uv run pytest tests/test_browser_job_table.py -k lists_all_jobs`
  - API 回傳全部職缺與順序：`uv run pytest tests/test_web_job_table.py -k get_jobs`
- [AC-query-columns](../../product/features/job-database.md#ac-query-columns選欄位)：`uv run pytest tests/test_browser_job_table.py -k columns`，以及 `npm test --prefix frontend -- columns`
- [AC-query-sort](../../product/features/job-database.md#ac-query-sort排序)：`uv run pytest tests/test_browser_job_table.py -k sort`，以及 `npm test --prefix frontend -- sort`
- [AC-query-expand](../../product/features/job-database.md#ac-query-expand展開一列)：`uv run pytest tests/test_browser_job_table.py -k expand`
  - 連結開在新分頁時攔下請求，不真的連到 104。
- [AC-query-filter](../../product/features/job-database.md#ac-query-filter關鍵字與地區篩選)：`uv run pytest tests/test_browser_job_table.py -k filter`，以及 `npm test --prefix frontend -- filter`
- [AC-query-remember](../../product/features/job-database.md#ac-query-remember記住欄位篩選與排序)：`uv run pytest tests/test_browser_job_table.py -k "remembers_view or storage_blocked"`，以及 `npm test --prefix frontend -- view storage`
  - 不允許保存的瀏覽器：以 Playwright 的 init script 讓讀取 `localStorage` 丟出例外。
- [AC-query-reset](../../product/features/job-database.md#ac-query-reset還原預設檢視)：`uv run pytest tests/test_browser_job_table.py -k reset_view`，以及 `npm test --prefix frontend -- view`

### just-saved

- [AC-just-saved-list](../../product/features/job-database.md#ac-just-saved-list只列出剛存入的職缺)：`uv run pytest tests/test_browser_job_table.py -k just_saved`，以及 `npm test --prefix frontend -- justSaved view`

### 共用規則

- [AC-db](../../product/features/job-database.md#ac-db自動建立資料庫)：`uv run pytest tests/test_job_db.py -k open_db`，以及 `git check-ignore data/jobs.db`
  - 通過條件：pytest 全部 passed，`git check-ignore` 印出路徑
