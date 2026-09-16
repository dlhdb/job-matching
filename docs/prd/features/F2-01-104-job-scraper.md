# F2-01 104 職缺爬蟲

| 欄位 | 內容 |
| :--- | :--- |
| ID | F2-01 |
| 核心技術 | 2 — 從求職平台獲取職缺資訊（見 [PRD 索引](../README.md#核心技術)） |
| 狀態 | ✅ 已完成 |
| 依賴 | 無 |
| 技術規格 | [104-scraper.md](../../spec/104-scraper.md) |

## 1. 背景與目標

在 104 人力銀行網站上手動複製職缺很耗時，且搜尋結果只提供截斷的工作描述。
本功能依關鍵字與地區批量抓取 104 職缺，產出結構化資料，作為後續 AI 評分（F4）的輸入。

## 2. 使用情境

- 身為求職者，我想要輸入多個關鍵字與縣市，一次取得不重複的職缺清單，以便不必逐頁瀏覽 104。
- 身為求職者，我想要用 Excel 直接開啟結果，以便快速瀏覽與篩選。
- 身為後續的 AI 分析流程，我需要完整的工作內容與固定的欄位結構，以便穩定地評分。

## 3. 範圍

**範圍內**

- 104 搜尋 API 與職缺詳情 API
- CLI 參數模式與互動引導模式
- 輸出 CSV 與 JSON

**範圍外**

- 其他求職平台（另開 F2-xx）
- 公司評價資訊（屬 F3）
- 排程定期執行、資料庫儲存
- 跨次執行的去重（去重只在單次執行內）

## 4. 功能需求

- **FR-1**：支援以 `-k/--keyword`、`-p/--pages`、`-a/--area`、`-t/--type` 參數執行；未帶 `--keyword` 時進入互動引導模式。
- **FR-2**：多個關鍵字可用半形或全形逗號分隔，逐一搜尋；重複的關鍵字只搜尋一次，保留首次出現的順序。
- **FR-3**：縣市名稱可精準或模糊比對（如 `台北`）到 104 地區代碼；無法辨識或未填時搜尋全台灣。
- **FR-4**：單次執行內，以 `職缺代碼` 去重，輸出中每筆職缺唯一。
- **FR-5**：對每筆職缺呼叫詳情 API 取得完整「工作內容」與「薪資待遇」；詳情失敗時兩欄為 `null`，不以搜尋摘要回填。
- **FR-6**：輸出 CSV（`utf-8-sig` 編碼）與 JSON（UTF-8）到 `output/104/`，欄位順序固定為 `CSV_FIELDNAMES`。
- **FR-7**：請求須帶 `User-Agent` 與 `Referer` 標頭並設 `timeout`；分頁間延遲 1.0–2.0 秒、關鍵字間 2.0–3.5 秒、詳情請求前 0.1–0.3 秒。
- **FR-8**：日期欄位由 `YYYYMMDD` 轉為 `YYYY-MM-DD`；職缺與公司連結轉為完整 `https://` URL。
- **FR-9**：使用者按下 Ctrl+C 時印出取消訊息並以結束碼 0 退出。

## 5. 輸入 / 輸出契約

- **輸入**：CLI 參數或互動輸入，定義見 [104-scraper.md §4.2](../../spec/104-scraper.md)。
- **輸出**：`output/104/jobs_104_<關鍵字>_<timestamp>.csv` 與 `.json`，欄位定義見 [104-scraper.md §3](../../spec/104-scraper.md)。
- **缺值處理**：`薪資待遇`、`工作內容`、`薪資下限`、`薪資上限` 可能為 `null`，下游必須容忍。

## 6. 驗收標準

測試都在 [tests/test_fetch_104_jobs.py](../../../tests/test_fetch_104_jobs.py)。除了 AC-5，其餘都離線執行：API 請求與等待都以 monkeypatch 取代，檔案寫到暫存目錄。

一次跑完所有離線驗收：

```bash
uv run pytest tests/test_fetch_104_jobs.py
```

### AC-1：關鍵字拆分（涵蓋 FR-2）

- **Given**：關鍵字字串混用半形、全形逗號與空白，或含重複的關鍵字
- **When**：呼叫 `parse_keywords`
- **Then**：得到去除空白、不重複且保留原順序的關鍵字列表
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k parse_keywords`
- **通過條件**：全部 passed。

### AC-2：地區解析（涵蓋 FR-3）

- **Given**：輸入精準名稱、模糊名稱、無法辨識的名稱與空值
- **When**：呼叫 `resolve_area`
- **Then**：前兩者得到正確代碼（`新竹` 對應新竹市），後兩者得到 `(None, "全台灣")`
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k resolve_area`
- **通過條件**：全部 passed。

### AC-3：欄位解析與詳情失敗時不回填（涵蓋 FR-5、FR-8）

- **Given**：含搜尋摘要的原始職缺；詳情 API 分別成功、失敗（回傳 `None`），以及職缺連結中沒有 job id
- **When**：呼叫 `parse_jobs`
- **Then**：詳情成功時填入完整的工作內容與薪資待遇；失敗時兩欄為 `None`，不以搜尋摘要回填；日期與連結已正規化；欄位順序等於 `CSV_FIELDNAMES`
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "parse_jobs or format_date or normalize_url or extract"`
- **通過條件**：全部 passed。

### AC-4：請求標頭、逾時與頻率限制（涵蓋 FR-7）

- **Given**：以假函式取代 `requests.get` 與 `time.sleep`，並記錄呼叫參數
- **When**：呼叫 `fetch_jobs`、`fetch_job_detail`、`execute_scraping`
- **Then**：每個請求都帶 `User-Agent`、`Referer` 與 `timeout`；詳情請求的 Referer 是職缺自己的頁面；分頁間、關鍵字間、詳情請求前的延遲都在規定範圍內；HTTP 錯誤或網路例外時回傳空結果，不會讓程式中斷
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "fetch_job or dedups"`
- **通過條件**：全部 passed。

### AC-5：去重、輸出檔與 CLI（涵蓋 FR-1、FR-4、FR-6）

- **Given**：以假資料取代搜尋 API，兩個關鍵字的結果有重疊
- **When**：呼叫 `execute_scraping`，以及用不同參數呼叫 `main` 和 `run_interactive`
- **Then**：輸出中每筆職缺唯一；產生同名的 CSV（以 BOM 開頭、表頭等於 `CSV_FIELDNAMES`）與 JSON；到達最後一頁或遇到空頁時停止；有帶 `--keyword` 時使用 CLI 模式，沒帶時進入互動模式
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k "execute_scraping or save or main or interactive"`
- **通過條件**：全部 passed。

### AC-6：Ctrl+C 優雅退出（涵蓋 FR-9）

- **Given**：程式處於互動模式等待輸入
- **When**：送出 SIGINT
- **Then**：印出取消訊息，結束碼為 0
- **驗證方式**：`uv run pytest tests/test_fetch_104_jobs.py -k ctrl_c`
- **通過條件**：passed。

### AC-7：實際抓取與輸出 〔需網路〕（涵蓋 FR-1、FR-4、FR-5、FR-6）

- **Given**：可以連線到 104
- **When**：以兩個搜尋結果會重疊的關鍵字（`Python`、`Python工程師`）、1 頁、台北市執行抓取，輸出寫到暫存目錄
- **Then**：職缺代碼不重複，而且少於兩個關鍵字抓到的原始筆數（代表跨關鍵字去重有生效）；CSV 以 BOM 開頭且表頭一致；至少一筆有完整的工作內容
- **驗證方式**：`uv run pytest -m network tests/test_fetch_104_jobs.py`
- **通過條件**：passed。

## 7. 待決問題

無。
