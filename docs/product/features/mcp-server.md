# MCP 介面

- ID：mcp-server
- 狀態：待規劃
- 依賴：104-job-scraper（抓取）、job-database（職缺資料庫）、job-scoring（評分，含[依分數查詢職缺](job-scoring.md#7-依分數查詢職缺store)與[重跑時不重複付 AI 費用](job-scoring.md#8-重跑時不重複付-ai-費用cache)）

## 1. 背景與目標

目前的問題：

- 抓取、評分都要在終端機下指令。
- 結果散在 `output/` 的檔案與職缺資料庫。
- 想問「這週新出現、分數高的職缺有哪些」時，得自己寫查詢或開 notebook。

本功能提供一個本機的 MCP server，讓 Claude Code 這類 agent 以 tool 的形式抓取、評分與查詢職缺：

- 不必設計 UI，用對話就能完成 UP-01、UP-02 的操作。
- agent 可以把查詢結果交給自己的其他工具接著處理。

固定的抓取、評分流程直接執行 CLI，不經過本功能，避免每次都多付一層 agent 的 LLM 費用。

## 2. 範圍

範圍內（實作時只做這些）：

- 使用者故事，一個故事一章，細節見各章的「需求」：
  - [叫 agent 抓職缺](#4-叫-agent-抓職缺search)（`search`）：〔規劃中〕
  - [叫 agent 評分剛抓到的職缺](#5-叫-agent-評分剛抓到的職缺score)（`score`）：〔規劃中〕
  - [用條件查詢職缺](#6-用條件查詢職缺query)（`query`）：〔規劃中〕
  - [看單筆職缺的完整內容與評分理由](#7-看單筆職缺的完整內容與評分理由detail)（`detail`）：〔規劃中〕
- [§8 非功能需求](#8-非功能需求)：抓取數量上限、評分交給專案內的評分功能、缺值回傳 `null`
- [§9 共用規則](#9-共用規則)：啟動與註冊方式、進度訊息的輸出、錯誤處理

範圍外（實作時不要做）：

- 評分結果的保存與快取規則：屬 [job-scoring §7](job-scoring.md#7-依分數查詢職缺store)、[§8](job-scoring.md#8-重跑時不重複付-ai-費用cache)，本功能只呼叫它
- 修改個人資料檔（`profile/`）的 tool：偏好與經歷由使用者自己編輯
- 讓 agent 選擇 LLM 供應商或模型：一律使用 job-scoring 的預設值
- 查看抓取紀錄的 tool：`score_jobs` 需要的執行編號由 `search_104_jobs` 回傳，其他情況用不太到

## 3. 輸入與輸出

- 職缺資料庫：
  - 職缺與每次執行的紀錄見 [job-database 的保存的資訊](job-database.md#721-保存的資訊)。
  - 評分結果見 [job-scoring 的儲存的評分資訊](job-scoring.md#721-儲存的評分資訊)，每筆職缺只有最新一次的結果。
- 抓取：沿用 104-job-scraper，請求頻率與輸出檔見 [104-job-scraper 的非功能需求](104-job-scraper.md#7-非功能需求)、[輸出檔](104-job-scraper.md#621-輸出檔)。
- 評分：沿用 job-scoring，流程見 [job-scoring §4.2.3](job-scoring.md#423-評分流程)、[§6](job-scoring.md#6-一次評完整批並拿到結果檔batch)。
  - 個人資料檔讀取 `profile/`。
  - API key 讀取 `.env`。
- tool 回傳 JSON，鍵名使用中文，與爬蟲、評分的輸出一致。

## 4. 叫 agent 抓職缺（search）

身為求職者，我想要叫 agent 用幾個關鍵字抓一次職缺，以便不必記爬蟲的參數（UP-01）。

### 4.1 需求

- FR-search：`search_104_jobs` 依 [§4.2](#42-規則) 抓取 104 職缺。
  - 結果寫入 CSV、JSON 與職缺資料庫。
  - 回傳這次執行的摘要。

### 4.2 規則

`search_104_jobs`：抓取並寫入職缺資料庫。

- `keywords`（list[str]）：必填，1–5 個關鍵字
- `area`（str | null）：縣市名稱，規則同 104-job-scraper CLI 的 `-a`
  - `null` 代表全台灣
- `pages`（int）：每個關鍵字抓幾頁，1–5，預設 1
- `job_type`（int）：`0`／`1`／`2`，意義同 [104-job-scraper 的 CLI](104-job-scraper.md#822-cli)，預設 `0`

- 回傳：`執行編號`、`職缺數`、`新增`、`更新`、`JSON 檔`。
- 沒有抓到任何職缺時不算錯誤，回傳 `職缺數` 為 0、`執行編號` 為 `null`。
- `keywords` 與 `pages` 的上限見 [§8](#8-非功能需求)。

### 4.3 驗收

#### AC-search：抓取

- Given：
  - 不實際連線到 104，以固定的搜尋結果代替，也不實際等待
  - 輸出檔與資料庫都寫到測試用的位置
- When：呼叫 `search_104_jobs`
- Then：
  - 回傳的 `新增`、`更新` 與資料庫內容一致，並多一筆執行紀錄
  - 抓取的進度訊息沒有混進給 agent 的回應
  - `keywords` 為空或超過 5 個、`pages` 不在 1–5 時，回傳 tool error，且沒有向 104 發出請求
- 通過條件：全部符合。

## 5. 叫 agent 評分剛抓到的職缺（score）

身為求職者，我想要叫 agent 對剛抓到的職缺評分，並列出分數最高的幾筆與理由，以便只細看少數職缺（UP-02）。

列出分數最高的幾筆與理由，由 agent 接著呼叫 [§6](#6-用條件查詢職缺query) 與 [§7](#7-看單筆職缺的完整內容與評分理由detail) 的 tool 完成。

### 5.1 需求

- FR-score：`score_jobs` 依 job-scoring 的流程評分指定的職缺。
  - 評分結果依 job-scoring 的規則保存。
  - 回傳每筆的精簡結果與摘要。
  - 單筆失敗不中斷。
  - 以 `limit` 參數限制每次評分的筆數並設上限，避免塞滿 agent 的 context。

### 5.2 規則

`score_jobs`：評分並保存結果。

- `run_id`（int | null）：評這次執行抓到的職缺
- `job_nos`（list[str] | null）：評指定的職缺代碼
- `limit`（int）：最多評幾筆，1–50，預設 20

- `run_id` 與 `job_nos` 必須剛好給一個，否則回傳 tool error。
- `run_id` 取自 `search_104_jobs` 的回傳。
- 評分流程：
  1. 從職缺資料庫讀取職缺內容。
  2. 依 job-scoring 的整批評分逐筆評分（見 [job-scoring §7.2.2](job-scoring.md#722-流程)）。
  3. 評分結果依 [job-scoring 的儲存的評分資訊](job-scoring.md#721-儲存的評分資訊) 保存。
- `job_nos` 中有代碼不在職缺資料庫時，回傳 tool error，不評任何一筆。
- 職缺依該次執行出現的順序或 `job_nos` 的順序處理：
  - 超過 `limit` 的部分不評分，列在回傳的 `未處理`。
  - agent 可以再呼叫一次，評完剩下的職缺。
- 回傳：
  - 摘要：`成功`、`沿用`、`淘汰`、`失敗`、`未處理`。`沿用` 是沿用上次 AI 評分的筆數（見 [job-scoring §8.2.2](job-scoring.md#822-沿用時的行為)），算在 `成功` 裡。
  - 每筆的 `職缺代碼`、`職缺名稱`、`總分`、`淘汰`、`評語`、`失敗原因`。
  - 不含各維度理由，要看時用 `get_job_detail`。
- 整批評分可能跑好幾分鐘，超過 client 的 tool 逾時。因應方式：
  - 用 `limit` 控制每次的筆數。
  - 每筆開始時向 agent 回報進度（agent 支援時）。
- 缺少 API key、不支援的供應商時回傳 tool error，同 [job-scoring §6.2.1](job-scoring.md#621-流程)。

### 5.3 驗收

#### AC-score：評分

- Given：
  - 資料庫中有一次執行，含會被淘汰、會評分成功、會評分失敗的職缺各一筆
  - AI 的回應以固定內容代替，不實際呼叫 AI
  - 測試用的個人資料檔
- When：以 `run_id` 呼叫 `score_jobs`，再分別以錯誤的參數組合、`limit=1` 呼叫
- Then：
  - 摘要為成功 1、淘汰 1、失敗 1
  - 成功與淘汰的兩筆保存了評分結果，失敗的那筆沒有
  - 以同一個 `run_id` 再呼叫一次時，只對失敗那筆呼叫 AI，摘要的 `沿用` 為 1（`成功` 仍為 1）
  - `job_nos` 含不存在的代碼時，回傳 tool error，沒有呼叫 AI
  - `run_id` 與 `job_nos` 同時給或都不給時，回傳 tool error
  - `limit=1` 時只評一筆，其餘列在 `未處理`
  - 個人資料檔缺少、缺少 API key 時回傳 tool error
- 通過條件：全部符合。

## 6. 用條件查詢職缺（query）

身為求職者，我想要問「最近一週新出現、70 分以上的職缺」，以便不必自己寫查詢（UP-02）。

### 6.1 需求

- FR-query：`query_jobs` 依分數、首次出現時間、關鍵字篩選職缺。
  - 依 [§6.2](#62-規則) 的規則排序。
  - 回傳精簡欄位。
  - 以 `limit` 參數限制回傳的筆數並設上限，避免塞滿 agent 的 context。

### 6.2 規則

`query_jobs`：查詢職缺。

- `min_score`（int | null）：只回傳 `總分` ≥ 此值的職缺
  - 會排除未評分的職缺
- `since`（str | null）：只回傳 `首次出現時間` ≥ 此日期（`YYYY-MM-DD`）的職缺
- `keyword`（str | null）：`職缺名稱` 或 `公司名稱` 包含此字串，不分大小寫
- `include_eliminated`（bool）：是否包含被淘汰的職缺，預設 `false`
- `limit`（int）：1–100，預設 20

- 排序：
  1. `總分` 由高到低，未評分的排在最後。
  2. 同分時 `首次出現時間` 較新的在前。
- 回傳：
  - 每筆的 `職缺代碼`、`職缺名稱`、`公司名稱`、`薪資待遇`、`總分`、`評語`、`首次出現時間`、`職缺連結`
  - `符合筆數`：套用 `limit` 前的總數
- 未評分的職缺照常出現在結果中，`總分`、`評語` 為 `null`。
- `include_eliminated` 為 `false` 時只排除被淘汰的職缺，未評分的職缺**不會**被排除。

### 6.3 驗收

#### AC-query：查詢

- Given：資料庫中有以下職缺
  - a：`職缺名稱` 為 `Python 工程師`，總分 85，未淘汰，首次出現 2026-09-10
  - b：`職缺名稱` 為 `資料工程師`，總分 60，未淘汰，首次出現 2026-09-16
  - c：`職缺名稱` 為 `業務專員`，被淘汰（總分 null），首次出現 2026-09-16
  - d：`職缺名稱` 為 `python 後端`，未評分，首次出現 2026-09-17
- When → Then：每項是「參數 → 依序回傳的職缺」
  - 無參數 → a、b、d
  - `min_score=70` → a
  - `since="2026-09-16"` → b、d
  - `keyword="python"` → a、d
  - `include_eliminated=true` → a、b、d、c（c、d 都沒有總分，d 較新所以在前）
  - `limit=1` → a，`符合筆數` 為 3
  - `limit=101` → tool error
- 通過條件：全部符合。

## 7. 看單筆職缺的完整內容與評分理由（detail）

身為求職者，我想要看到某筆職缺的完整內容與各維度的評分理由，以便決定要不要細看（UP-02）。

### 7.1 需求

- FR-detail：`get_job_detail` 回傳單筆職缺的全部欄位，以及保存的評分結果中各維度的分數與理由。

### 7.2 規則

`get_job_detail`：查看單筆職缺。

- 參數：`job_no`（str，必填）。
- 回傳：職缺的全部欄位（見 [job-database 的保存的資訊](job-database.md#721-保存的資訊)），加上 `評分`。
  - `評分` 是保存的完整評分結果，格式同 [job-scoring §11.2.1](job-scoring.md#1121-評分結果格式)。
  - 尚未評分時 `評分` 為 `null`。
- 找不到職缺時回傳 tool error。

### 7.3 驗收

#### AC-detail：單筆職缺

- Given：同 [AC-query](#ac-query查詢) 的資料庫
- When：呼叫 `get_job_detail("a")`、`get_job_detail("d")`
- Then：
  - `a` 的 `評分` 含四個維度的分數與理由
  - `d` 的 `評分` 為 `null`
- 通過條件：全部符合。

## 8. 非功能需求

### 8.1 需求

- NFR-rate：`search_104_jobs` 的 `keywords` 最多 5 個、`pages` 最多 5 頁。
  - 避免 agent 一次發出大量請求，違反 [非目標](../overview.md#非目標) 的頻率限制。
  - 請求之間的延遲沿用 104-job-scraper（見 [104-job-scraper 的非功能需求](104-job-scraper.md#7-非功能需求)）。
- NFR-cost：評分由專案內的評分功能執行，不讓 agent 自己打分。
  - 這樣才能用上 job-scoring 的評分快取：送給 AI 的內容沒變的職缺，不重複呼叫 AI（見 [job-scoring §8.2.1](job-scoring.md#821-快取鍵)）。
- NFR-null：缺值時回傳 `null`，不回填（依 [development.md](../../conventions/development.md#防禦性設計)）。
  - 職缺欄位與評分欄位缺值時為 `null`。
  - 尚未評分的職缺，評分相關欄位都是 `null`。

### 8.2 規則

- 評分交給專案內評分功能的其他理由：分數依同一套偏好檔、提示詞與模型產生，不同 agent 或不同次對話的結果可以比較。
- 缺值與未評分的處理見 [§6.2](#62-規則) 與 [§7.2](#72-規則) 的 `評分`。

### 8.3 驗收

本章的需求由各章既有的驗收涵蓋，不另外寫：

- NFR-rate：[AC-search](#ac-search抓取)（`keywords`、`pages` 超出範圍時回傳 tool error，且沒有發出請求）
- NFR-cost：[AC-score](#ac-score評分)（再呼叫一次時，只對失敗那筆呼叫 AI）
- NFR-null：
  - [AC-query](#ac-query查詢)（未評分的 d 照常出現）
  - [AC-detail](#ac-detail單筆職缺)（`d` 的 `評分` 為 `null`）

## 9. 共用規則

跨越各章的規則：啟動與註冊方式、進度訊息的輸出、錯誤處理。

### 9.1 需求

- FR-server：`uv run src/mcp_server.py` 啟動 MCP server，供本機的 agent 連線。
  - `--db` 可指定資料庫路徑，預設為 `data/jobs.db`（同 [job-database 的資料庫預設路徑](job-database.md#71-需求)）。
  - 專案根目錄的 `.mcp.json` 註冊這個 server，設定見 [§9.2.1](#921-註冊)。
- FR-output：tool 執行期間，抓取與評分的進度訊息不會混進給 agent 的回應，避免 agent 無法解析回應。
- FR-error：下列情況以 tool error 回傳訊息，server 繼續執行：
  - 參數錯誤
  - 找不到職缺
  - 個人資料檔有誤
  - 缺少 API key

### 9.2 規則

- 每個 tool 的行為與對應的 CLI 一致：抓取同 104-job-scraper，評分同 job-scoring。

#### 9.2.1 註冊

專案根目錄的 `.mcp.json` 讓 Claude Code 在這個專案中自動載入 server：

```json
{
  "mcpServers": {
    "job-radar": {
      "command": "uv",
      "args": ["run", "src/mcp_server.py"]
    }
  }
}
```

### 9.3 驗收

#### AC-server：啟動、tool 清單與錯誤不中斷

- Given：一個空的資料庫
- When：
  1. 以該資料庫啟動 server
  2. 以 MCP client 列出 tools
  3. 依序呼叫 `get_job_detail`（不存在的代碼）、`query_jobs`
- Then：
  - 列出的 tool 剛好是 §4–§7 的四個
  - `get_job_detail` 回傳 tool error，之後的 `query_jobs` 仍正常回傳空清單
  - agent 端沒有出現無法解析回應的錯誤
- 通過條件：全部符合。

#### AC-agent-real：在 Claude Code 中實際使用 〔需網路〕

- Given：
  - `profile/` 已填入真實資料
  - `.env` 有 API key
- When：在專案目錄開啟 Claude Code，確認 `job-radar` server 已載入，請 agent 依序做這幾件事：
  1. 抓取一個關鍵字、1 頁
  2. 評分其中 5 筆
  3. 列出分數最高的 3 筆，並說明第一名的理由
- Then：
  - agent 依序呼叫 `search_104_jobs`、`score_jobs`、`query_jobs`、`get_job_detail`，都沒有出現 tool error
  - 回答中的分數與理由，與資料庫中的內容一致
  - 另外以一個關鍵字、1 頁實際呼叫 `search_104_jobs`，自動檢查回傳與資料庫一致
- 通過條件：
  - 自動檢查全部符合
  - 使用者確認 agent 的回答與資料庫內容一致

## 10. 待決問題

無。
