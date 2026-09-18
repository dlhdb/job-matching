# 104 職缺爬蟲

| 欄位 | 內容 |
| :--- | :--- |
| ID | 104-job-scraper |
| 狀態 | ✅ 已完成 |
| 依賴 | 無 |
| 程式碼 | [src/fetch_104_jobs.py](../../src/fetch_104_jobs.py)（單檔自足腳本） |

## 1. 背景與目標

在 104 人力銀行網站上手動複製職缺很耗時，且搜尋結果只提供截斷的工作描述。
本功能依關鍵字與地區批量抓取 104 職缺，產出結構化資料，作為後續職缺評分的輸入（UP-01）。

## 2. 範圍

**範圍內**：見 [§3 設計總覽](#3-設計總覽)的使用者故事清單，以及 [§7 非功能需求](#7-非功能需求)、[§8 共用設計](#8-共用設計)。

**範圍外**（實作時不要做）

- 其他求職平台（另開一個功能）
- 公司評價資訊（屬 company-info）
- 資料庫儲存（屬 job-database）
- 排程定期執行（目前不規劃，見 [非目標](../README.md#非目標)）
- 跨次執行的去重（去重只在單次執行內，跨次去重屬 job-database）

## 3. 設計總覽

**輸入與輸出**

- 輸入：使用者給的搜尋條件（關鍵字、縣市、頁數、職缺性質，見 [§8.2.2](#822-cli)），以及 104 的搜尋與詳情 API（見 [§4.2.2](#422-104-api-的限制)）。沒有上游功能。
- 輸出：`output/104/` 下同名的 CSV 與 JSON（見 [§6.2.1](#621-輸出檔)），欄位依 [§8.2.1](#821-欄位字典) 的欄位字典。
  - JSON 給 job-scoring 評分，也給 [job-database](job-database.md) 匯入資料庫。評分需要完整的工作內容與固定的欄位結構，才能穩定地評分，所以欄位字典是對下游的資料契約。
  - CSV 供人用 Excel 瀏覽。
- 抓完後預設由 job-database 把同一批職缺寫進 `data/jobs.db`（見 [job-database 的爬蟲寫入參數](job-database.md#423-爬蟲的寫入參數)）。

**使用者故事清單**

本功能範圍內的使用者故事，細節見各章的「需求」。

| 使用者故事 | slug | 狀態 | 章節 |
| :--- | :--- | :--- | :--- |
| 一次搜尋多個關鍵字與縣市，拿到不重複的職缺 | `search` | ✅ | [§4](#4-一次搜尋多個關鍵字與縣市拿到不重複的職缺search) |
| 每筆職缺都有完整的工作內容 | `detail` | ✅ | [§5](#5-每筆職缺都有完整的工作內容detail) |
| 用 Excel 或程式開啟結果 | `output` | ✅ | [§6](#6-用-excel-或程式開啟結果output) |

[§7 非功能需求](#7-非功能需求)與 [§8 共用設計](#8-共用設計)不是使用者故事。§8 放跨越各章的基礎設施：欄位字典與 CLI。

## 4. 一次搜尋多個關鍵字與縣市，拿到不重複的職缺（search）

身為求職者，我想要輸入多個關鍵字與縣市，一次取得不重複的職缺清單，以便不必逐頁瀏覽 104。

### 4.1 需求

- **FR-search-keyword**：多個關鍵字可用半形或全形逗號分隔，逐一搜尋。
  - 重複的關鍵字只搜尋一次，保留首次出現的順序。
- **FR-search-area**：縣市名稱可精準或模糊比對（如 `台北`）到 104 地區代碼。
  - 無法辨識或未填時搜尋全台灣。
- **FR-search-dedup**：單次執行內，以 `職缺代碼` 去重，輸出中每筆職缺唯一。
- **FR-search-request**：請求須帶 `User-Agent` 與 `Referer` 標頭並設 `timeout`。
  - 請求之間的延遲見 [§7](#7-非功能需求)。

### 4.2 設計

#### 4.2.1 流程

1. `main()` 解析參數；有 `--keyword` 走 CLI 模式，否則 `run_interactive()` 逐步詢問關鍵字、縣市、頁數與職缺性質。兩種模式共用 `parse_keywords()` 與 `resolve_area()`。
2. `execute_scraping()` 對每個關鍵字逐頁呼叫搜尋 API（`fetch_jobs()`），遇到空頁或已到 `lastPage` 就換下一個關鍵字。
3. 所有關鍵字抓完後，`parse_jobs()` 對每筆去重後的職缺呼叫詳情 API（`fetch_job_detail()`，見 [§5](#5-每筆職缺都有完整的工作內容detail)），並轉成中文鍵名的 dict。
4. 寫出 CSV 與 JSON（見 [§6](#6-用-excel-或程式開啟結果output)），並在終端機印出前 10 筆的預覽表格。

#### 4.2.2 104 API 的限制

| API | URL | 備註 |
| :--- | :--- | :--- |
| 搜尋 | `https://www.104.com.tw/jobs/search/api/jobs` | `timeout=10`；回傳的 `description` 只是關鍵字高亮的截斷摘要 |
| 詳情 | `https://www.104.com.tw/job/ajax/content/{job_id}` | `timeout=5`；`job_id` 是職缺連結中 `/job/` 後面的 base36 代碼（如 `8s12x`） |

- 缺少 `User-Agent` 或 `Referer` 時，104 一律回 403，所以兩個標頭都放在 `DEFAULT_HEADERS`，不可移除。搜尋 API 的 Referer 是 `https://www.104.com.tw/jobs/search/`。`Accept-Language` 設為 `zh-TW` 優先，讓回傳內容是繁體中文。
- 詳情 API 會檢查 Referer 是否為該職缺自己的頁面（`https://www.104.com.tw/job/{job_id}`），沿用搜尋頁的 Referer 會被擋。
- 詳情請求不加延遲會被 104 拒絕，延遲規則見 [§7.2](#72-設計)。
- 搜尋 API 回非 200 或拋出網路例外時，該頁視為空頁（回傳空結果），不讓程式中斷。詳情 API 失敗時的處理見 [§5.2](#52-設計)。

#### 4.2.3 地區與去重

- `resolve_area()` 依 `POPULAR_AREAS`（22 個縣市）比對：先找完全相同的名稱，找不到再找「輸入是縣市名的子字串，或縣市名是輸入的子字串」的第一筆。因此 `新竹` 會對到清單中先出現的新竹市，要找新竹縣必須寫全名；`臺北`（異體字）比對不到，會退回全台灣。
- 去重用 `seen_job_nos` 集合記錄 `jobNo`，同一個關鍵字的不同分頁、不同關鍵字之間都會去重。集合只存在於單次執行中。

### 4.3 驗收

本功能的離線測試都在 [tests/test_fetch_104_jobs.py](../../tests/test_fetch_104_jobs.py)，API 請求與等待都以 monkeypatch 取代，檔案寫到暫存目錄。

#### AC-search-keyword：關鍵字拆分

- **Given**：關鍵字字串混用半形、全形逗號與空白，或含重複的關鍵字
- **When**：呼叫 `parse_keywords`
- **Then**：得到去除空白、不重複且保留原順序的關鍵字列表
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k parse_keywords`
- **通過條件**：全部 passed。

#### AC-search-area：地區解析

- **Given**：輸入精準名稱、模糊名稱、無法辨識的名稱與空值
- **When**：呼叫 `resolve_area`
- **Then**：前兩者得到正確代碼（`新竹` 對應新竹市），後兩者得到 `(None, "全台灣")`
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k resolve_area`
- **通過條件**：全部 passed。

#### AC-search-dedup：去重與分頁

- **Given**：以假資料取代搜尋 API，兩個關鍵字的結果有重疊
- **When**：呼叫 `execute_scraping`
- **Then**：輸出中每筆職缺唯一；到達最後一頁或遇到空頁時停止
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "dedups or stops_on_empty_page or respects_page_limit or accepts_single_string"`
- **通過條件**：全部 passed。

#### AC-search-request：請求標頭、逾時與錯誤處理

- **Given**：以假函式取代 `requests.get`，並記錄呼叫參數
- **When**：呼叫 `fetch_jobs`、`fetch_job_detail`
- **Then**：每個請求都帶 `User-Agent`、`Referer` 與 `timeout`；詳情請求的 Referer 是職缺自己的頁面；HTTP 錯誤或網路例外時回傳空結果，不會讓程式中斷
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k fetch_job`
- **通過條件**：全部 passed。

#### AC-search-real：實際抓取與輸出 〔需網路〕

- **Given**：可以連線到 104
- **When**：以兩個搜尋結果會重疊的關鍵字（`Python`、`Python工程師`）、1 頁、台北市執行抓取，輸出寫到暫存目錄
- **Then**：職缺代碼不重複，而且少於兩個關鍵字抓到的原始筆數（代表跨關鍵字去重有生效）；CSV 以 BOM 開頭且表頭一致；至少一筆有完整的工作內容
- **驗證方式**：`uv run pytest -m network tests/e2e/test_fetch_104_jobs.py`
- **通過條件**：passed。

## 5. 每筆職缺都有完整的工作內容（detail）

身為求職者，我想要每筆職缺都有完整的工作內容與薪資待遇，以便不必逐筆點開 104 的頁面，評分時也能拿到完整的描述。

### 5.1 需求

- **FR-detail**：對每筆職缺呼叫詳情 API 取得完整「工作內容」與「薪資待遇」。
  - 詳情失敗時兩欄為 `null`，不以搜尋摘要回填。

### 5.2 設計

- 搜尋 API 的 `description` 只是截斷的摘要（見 [§4.2.2](#422-104-api-的限制)），所以每筆職缺都要另外呼叫詳情 API。
- 詳情 API 失敗時回傳 `None`；職缺連結解析不出 `job_id` 時不發詳情請求，兩者的結果相同：`薪資待遇` 與 `工作內容` 為 `null`，不用搜尋 API 的 `description` 回填。那只是截斷的摘要，回填會讓下游的 AI 收到看似完整、其實殘缺的資料。

### 5.3 驗收

#### AC-detail：欄位解析與詳情失敗時不回填

- **Given**：含搜尋摘要的原始職缺；詳情 API 分別成功、失敗（回傳 `None`），以及職缺連結中沒有 job id
- **When**：呼叫 `parse_jobs`
- **Then**：詳情成功時填入完整的工作內容與薪資待遇；失敗時兩欄為 `None`，不以搜尋摘要回填；欄位順序等於 `CSV_FIELDNAMES`
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "parse_jobs or extract"`
- **通過條件**：全部 passed。

## 6. 用 Excel 或程式開啟結果（output）

身為求職者，我想要用 Excel 直接開啟結果，以便快速瀏覽與篩選；同一份結果也要有 JSON，交給程式或 AI 做後續分析。

### 6.1 需求

- **FR-output-files**：輸出 CSV（`utf-8-sig` 編碼）與 JSON（UTF-8）到 `output/104/`。
  - 欄位順序固定為 `CSV_FIELDNAMES`（見 [§8.2.1](#821-欄位字典)）。
- **FR-output-format**：欄位格式正規化：
  - 日期欄位由 `YYYYMMDD` 轉為 `YYYY-MM-DD`。
  - 職缺與公司連結轉為完整 `https://` URL。

### 6.2 設計

#### 6.2.1 輸出檔

- 檔名是 `jobs_104_<關鍵字>_<YYYYMMDD_HHMMSS>.csv` 與 `.json`，寫在 `OUTPUT_DIR`（專案根目錄的 `output/104/`，以腳本位置推算，不受工作目錄影響，不存在時自動建立；已列入 `.gitignore`）。`<關鍵字>` 的產生規則：
  - 多個關鍵字以 `_` 連接，超過 30 字元就截斷並加上 `_etc`。
  - 只保留 `str.isalnum()` 為真的字元（含中文）與 `-`、`_`，例如 `jobs_104_後端工程師_…`。
  - 結果為空時用 `all`。
- CSV 用 `utf-8-sig` 編碼，開頭的 BOM 讓 Excel 把檔案當成 UTF-8，中文才不會亂碼。

### 6.3 驗收

#### AC-output-files：輸出檔

- **Given**：以假資料取代搜尋 API
- **When**：呼叫 `save_to_csv`、`save_to_json` 與 `execute_scraping`
- **Then**：產生同名的 CSV（以 BOM 開頭、表頭等於 `CSV_FIELDNAMES`）與 JSON；檔名依 [§6.2.1](#621-輸出檔) 的規則產生；沒有抓到職缺時不寫檔
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "save or execute_scraping_filename or execute_scraping_no_jobs"`
- **通過條件**：全部 passed。

#### AC-output-format：欄位格式正規化

- **Given**：`YYYYMMDD` 格式的日期、以 `//` 開頭的連結，以及空值
- **When**：呼叫 `format_date`、`normalize_url`
- **Then**：日期轉成 `YYYY-MM-DD`，連結轉成完整的 `https://` URL，空值轉成空字串
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "format_date or normalize_url"`
- **通過條件**：全部 passed。

## 7. 非功能需求

### 7.1 需求

- **NFR-rate**：請求之間要延遲，避免對 104 造成負擔（見 [非目標](../README.md#非目標)）：
  - 分頁間 1.0–2.0 秒。
  - 關鍵字間 2.0–3.5 秒。
  - 詳情請求前 0.1–0.3 秒。
- **NFR-null**：詳情 API 失敗時缺值為 `null`，不以其他來源回填（依 [development.md](../conventions/development.md#防禦性設計)，見 [§5](#5-每筆職缺都有完整的工作內容detail)）。

### 7.2 設計

- 詳情請求不加延遲會被 104 拒絕。
- 延遲都取隨機區間，讓請求分散，不集中在固定間隔送出。

### 7.3 驗收

#### AC-nfr-rate：請求頻率限制

- **Given**：以假函式取代 `requests.get` 與 `time.sleep`，並記錄呼叫參數
- **When**：呼叫 `parse_jobs`、`execute_scraping`
- **Then**：分頁間、關鍵字間、詳情請求前的延遲都在規定範圍內
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "dedups or parse_jobs_with_detail"`
- **通過條件**：全部 passed。

NFR-null 由 [AC-detail](#ac-detail欄位解析與詳情失敗時不回填) 涵蓋（詳情失敗時兩欄為 `None`），不另外寫測試。

## 8. 共用設計

跨越各章的基礎設施：欄位字典與 CLI。

### 8.1 需求

- **FR-cli**：支援以 `-k/--keyword`、`-p/--pages`、`-a/--area`、`-t/--type` 參數執行，參數依 [§8.2.2](#822-cli)。
  - 未帶 `--keyword` 時進入互動引導模式。
  - 使用者按下 Ctrl+C 時印出取消訊息並以結束碼 0 退出。

### 8.2 設計

#### 8.2.1 欄位字典

輸出使用中文鍵名，順序等於 `CSV_FIELDNAMES`。job-scoring 以這份字典作為輸入契約；新增欄位時要同步修改 `parse_jobs()`、`CSV_FIELDNAMES` 與本表。

| 欄位 | 來源 | 型態 | 說明 |
| :--- | :--- | :--- | :--- |
| `職缺代碼` | `jobNo` | str | 104 的職缺識別碼，用於去重 |
| `職缺名稱` | `jobName` | str | |
| `公司名稱` | `custName` | str | |
| `產業類別` | `coIndustryDesc` | str | 例如 `電腦系統整合服務業` |
| `地區` | `jobAddrNoDesc` + `jobAddress` | str | 以空白合併縣市行政區與街道地址 |
| `薪資待遇` | 詳情 API 的 `jobDetail.salary` | str \| null | 原始薪資描述，例如 `月薪60,000~70,000元`、`待遇面議`；詳情失敗時為 `null` |
| `薪資下限` | `salaryLow` | int \| null | 保留 API 原始值；面議時為 `0` |
| `薪資上限` | `salaryHigh` | int \| null | 保留 API 原始值；面議時為 `0`，沒有上限（如「月薪50,000元以上」）時為 `9999999`，下游以 ≥ 9999999 判斷 |
| `更新日期` | `appearDate` | str | 由 `YYYYMMDD` 轉成 `YYYY-MM-DD` |
| `應徵人數` | `applyCnt` | int | 缺值時為 `0` |
| `工作內容` | 詳情 API 的 `jobDetail.jobDescription` | str \| null | 完整工作描述；詳情失敗時為 `null` |
| `電腦專長` | `pcSkills[].description` | str | 以 `, ` 合併，例如 `Python, Git`；沒有時為空字串 |
| `科系要求` | `major` | str | 以 `, ` 合併；沒有時為空字串 |
| `特色標籤` | `tags` 的 `desc` | str | 以 `, ` 合併，例如 `週休二日, 距捷運站210公尺` |
| `職缺連結` | `link.job` | str | 轉成完整的 `https://` URL |
| `公司連結` | `link.cust` | str | 轉成完整的 `https://` URL |

#### 8.2.2 CLI

```bash
uv run src/fetch_104_jobs.py                                    # 互動模式
uv run src/fetch_104_jobs.py -k "關鍵字1,關鍵字2" -p 頁數 -a 縣市 -t 性質
```

| 參數 | 說明 |
| :--- | :--- |
| `-k`, `--keyword` | 搜尋關鍵字，多個用半形或全形逗號分隔；有帶這個參數才會走 CLI 模式 |
| `-p`, `--pages` | 每個關鍵字抓幾頁，每頁 30 筆，預設 `3` |
| `-a`, `--area` | 縣市名稱（比對規則見 [§4.2.3](#423-地區與去重)），不填代表全台灣 |
| `-t`, `--type` | 職缺性質：`0` 全部（預設）、`1` 全職、`2` 兼職／工讀 |

寫入職缺資料庫的 `--db`、`--no-db` 見 [job-database 的爬蟲寫入參數](job-database.md#423-爬蟲的寫入參數)。

按下 Ctrl+C 時，`__main__` 區塊會攔下 `KeyboardInterrupt`，印出取消訊息並以結束碼 0 結束。

一次跑完所有離線驗收：

```bash
uv run pytest tests/test_fetch_104_jobs.py
```

### 8.3 驗收

#### AC-cli：CLI 與互動模式

- **Given**：以假函式取代 `execute_scraping` 與輸入
- **When**：用不同參數呼叫 `main` 和 `run_interactive`
- **Then**：有帶 `--keyword` 時使用 CLI 模式，沒帶時進入互動模式；參數的預設值符合 [§8.2.2](#822-cli)
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "main_cli or main_without_keyword or run_interactive"`
- **通過條件**：全部 passed。

#### AC-cli-interrupt：Ctrl+C 優雅退出

- **Given**：程式處於互動模式等待輸入
- **When**：送出 SIGINT
- **Then**：印出取消訊息，結束碼為 0
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k ctrl_c`
- **通過條件**：passed。

## 9. 待決問題

無。
