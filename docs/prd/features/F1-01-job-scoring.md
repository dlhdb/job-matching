# F1-01 工作評分邏輯

| 欄位 | 內容 |
| :--- | :--- |
| ID | F1-01 |
| 核心技術 | 1 — 工作評分邏輯（見 [PRD 索引](../README.md#核心技術)） |
| 狀態 | 已完成 |
| 依賴 | F2-01（使用其輸出的職缺 JSON 作為輸入） |
| 技術規格 | [job-scoring.md](../../spec/job-scoring.md) |

## 1. 背景與目標

爬蟲一次會抓到上百筆職缺，逐筆閱讀並判斷是否適合自己，要花很多時間。
本功能根據使用者提供的**工作偏好**與**工作經歷**，對單筆職缺做多維度評分，並產出總分與簡短評語，讓使用者快速判斷哪些職缺值得細看、原因是什麼（UC-02）。批次評分與排序由 F4 負責，F4 會重複使用本功能的評分函式。

## 2. 使用情境

- 身為求職者，我想要把偏好和經歷寫成檔案，以便每次評分都依照同一套標準。
- 身為求職者，我想要看到每個維度的分數與理由，以便知道總分是怎麼來的，並判斷要不要相信它。
- 身為求職者，我想要明顯不合的職缺（薪資太低、不想去的公司）直接被淘汰，以便不浪費時間與 AI 費用。
- 身為調整提示詞的開發者，我想要在不呼叫 AI 的情況下看到完整的提示詞，以便反覆修改。
- 身為後續的 F4 工作流，我需要固定格式的評分結果與可替換的 LLM 供應商，以便批次處理。

## 3. 範圍

**範圍內**

- 讀取並驗證 `profile/preferences.yaml` 與 `profile/experience.md`，並提供 `.example` 範本
- 硬性淘汰規則
- 四個評分維度：職涯方向契合度、技能匹配度、產業公司吸引力（AI 判斷），以及薪資水準（程式計算）
- 加權總分（未知維度以 3 分代入）
- 提示詞模板
- LLM 供應商抽象層與 Gemini 實作
- 對單筆職缺評分的 CLI，包含 `--dry-run`

**範圍外**（實作時不要做）

- 批次評分、結果存檔、排序與篩選（屬 F4）
- OpenAI 或其他供應商的實作（只保留介面）
- 通勤便利度、資歷門檻、工作型態與福利、競爭程度／新鮮度等維度（後續另開功能）
- 公司評價資訊（屬 F3；本功能的產業公司吸引力只看產業類別與公司名稱）
- 修改爬蟲或擴充爬蟲欄位
- 評分結果快取、重試機制

## 4. 功能需求

- **FR-1**：從指定目錄讀取 `preferences.yaml` 與 `experience.md`；`preferences.yaml` 要依 [job-scoring.md §2.1](../../spec/job-scoring.md#21-preferencesyaml-欄位字典) 驗證，缺少欄位、型別錯誤或權重的鍵不符時報錯，不補預設值。真實個人資料檔不進版控，版控中提供 `.example` 範本。
- **FR-2**：依 [§4](../../spec/job-scoring.md#4-硬性淘汰規則) 檢查硬性淘汰條件，並收集所有淘汰原因；被淘汰的職缺不呼叫 AI。
- **FR-3**：依 [§5](../../spec/job-scoring.md#5-薪資換算與計分) 換算月薪並計算薪資分數；面議、時薪、日薪、論件計酬與缺值都視為未知（`null`），不會因此被淘汰。
- **FR-4**：由 AI 依 [§3.1](../../spec/job-scoring.md#31-ai-維度的錨點描述) 的錨點，為三個 AI 維度各給 1–5 分或 `null`，每個維度都附上理由，另外提供總評；AI 回應必須通過 schema 驗證，否則視為失敗。
- **FR-5**：依 [§6](../../spec/job-scoring.md#6-總分) 計算 0–100 的加權總分；分數為 `null` 的維度以 3 分代入，讓所有沒被淘汰的職缺都有可以互相比較的總分。
- **FR-6**：提供 `src/score_job.py` CLI，參數與結束碼依 [§8.5](../../spec/job-scoring.md#85-cli)；`--dry-run` 只印出提示詞，不建立 LLM client。
- **FR-7**：LLM 呼叫透過 `LLMClient` 介面與 `get_client(provider, model)` 工廠函式；預設使用 Gemini。API key 讀取環境變數 `GEMINI_API_KEY`，CLI 啟動時會從專案根目錄的 `.env` 載入，但不覆寫已存在的環境變數；`.env` 不進版控，版控中提供 `.env.example`。只有 `llm.py` 可以依賴特定供應商的 SDK。

## 5. 輸入 / 輸出契約

- **輸入**：
  - 職缺：F2-01 輸出的 JSON，欄位定義見 [104-scraper.md §3](../../spec/104-scraper.md#3-資料欄位對應字典-data-dictionary)
  - 個人資料：見 [job-scoring.md §2](../../spec/job-scoring.md#2-輸入個人資料檔)
- **輸出**：`JobScore` JSON，印到 stdout，欄位定義見 [job-scoring.md §7](../../spec/job-scoring.md#7-輸出jobscore)。
- **缺值處理**：職缺欄位為 `null` 或空字串時，在提示詞中以「（無資料）」標示。AI 維度由 AI 判斷剩下的資料是否足以評分，不足時給 `null`，不猜分數；薪資無法換算時由程式給 `null`。分數為 `null` 的維度都列入 `未知維度`。

## 6. 驗收標準

測試與實作一起撰寫，依 [conventions.md 的測試章節](../../spec/conventions.md#測試)。除了 AC-8，其餘都離線執行，也不需要 API key。

### 共用測試資料

放在 `tests/conftest.py` 的 fixture，各測試檔共用：

- **偏好檔**：以 `profile/preferences.example.yaml` 為基礎（順便確認範本本身合法），覆寫下列欄位後寫到 `tmp_path`：
  - `目標方向: [目標標記-AAA]`
  - `薪資: {期望月薪: 70000, 底線月薪: 55000, 年薪換算月數: 14}`
  - `淘汰條件: {公司: [乙公司], 職稱關鍵字: [業務]}`
  - `權重: {職涯方向契合度: 0.4, 技能匹配度: 0.25, 產業公司吸引力: 0.15, 薪資水準: 0.2}`
- **經歷檔**：內容為 `經歷標記-BBB`
- **職缺檔**：兩筆職缺，共用欄位為 甲公司、軟體及網路相關業、`月薪60,000~80,000元`（60000 / 80000）、工作內容 `工作標記-CCC`，`電腦專長` 與 `科系要求` 為空字串
  - `ok`：職缺名稱 `Python 工程師`，不會被淘汰
  - `out`：職缺名稱 `業務專員`，會被淘汰
- **假的 LLM client**：不連網，回傳固定的 `AIAssessment`，並記錄被呼叫的次數
- **禁止建立 client**：用 monkeypatch 把 `score_job.get_client` 換成一呼叫就讓測試失敗的函式，並把 `GEMINI_API_KEY` 設為空字串

一次跑完所有離線驗收：

```bash
uv run pytest tests/test_job_scoring_*.py tests/test_score_job_cli.py
```

### AC-0：型別檢查（涵蓋全部）

- **Given**：實作完成
- **When**：執行 mypy
- **Then**：沒有錯誤
- **驗證方式**：`uv run mypy src/`
- **通過條件**：輸出 `Success: no issues found`。

### AC-1：個人資料檔驗證與版控（涵蓋 FR-1、FR-6）

- **Given**：(a) `preferences.yaml` 缺少 `權重`；(b) `權重` 多了一個不存在的維度；(c) `底線月薪` 大於 `期望月薪`；(d) `淘汰條件.職稱關鍵字` 含空字串
- **When**：以 `--dry-run` 呼叫 CLI 的 `main`
- **Then**：四種情況都回傳 1，stderr 含 `[-]`；以 `git check-ignore` 檢查時，`profile/preferences.yaml`、`profile/experience.md`、`.env` 被忽略，對應的範本檔沒有被忽略
- **驗證方式**：`uv run pytest tests/test_job_scoring_profile.py`
- **通過條件**：全部 passed。

### AC-2：薪資計分與硬性淘汰（涵蓋 FR-2、FR-3）

- **Given**：共用的測試偏好（期望 70,000、底線 55,000、年薪 ÷14、排除「乙公司」與「業務」）
- **When**：以下表的職缺呼叫 `score_salary`、`check_hard_filters`（以 `parametrize` 實作）
- **Then**：分數與淘汰結果符合下表與 [job-scoring.md §4–5](../../spec/job-scoring.md#4-硬性淘汰規則)

  | 薪資待遇 | 下限 | 上限 | 薪資分數 | 淘汰原因 |
  | :--- | --: | --: | :-: | :--- |
  | `月薪70,000~90,000元` | 70000 | 90000 | 5 | 無 |
  | `月薪60,000~80,000元` | 60000 | 80000 | 4 | 無 |
  | `月薪56,000~60,000元` | 56000 | 60000 | 2 | 無 |
  | `年薪980,000~1,260,000元`（換算 70,000~90,000） | 980000 | 1260000 | 5 | 無 |
  | `月薪50,000元以上`（沒有上限） | 50000 | 9999999 | 2 | 無 |
  | `待遇面議` | 0 | 0 | `None` | 無 |
  | `時薪500元以上` | 500 | 9999999 | `None` | 無 |
  | `論件計酬3,000~15,000元` | 3000 | 15000 | `None` | 無 |
  | `None` | `None` | `None` | `None` | 無 |
  | `月薪40,000~50,000元` | 40000 | 50000 | — | 1 條，含「底線」 |
  | `年薪560,000~700,000元`（換算上限 50,000） | 560000 | 700000 | — | 1 條，含「底線」 |
  | `月薪40,000~50,000元`，職稱 `業務專員`，公司 `乙公司` | 40000 | 50000 | — | 3 條（收集所有原因） |

- **驗證方式**：`uv run pytest tests/test_job_scoring_rules.py`
- **通過條件**：全部 passed。

### AC-3：總分計算（涵蓋 FR-5）

- **Given**：權重 0.4 / 0.25 / 0.15 / 0.2
- **When**：以下表的分數組合呼叫 `compute_total`（以 `parametrize` 實作）
- **Then**：結果符合下表與 [§6](../../spec/job-scoring.md#6-總分) 的公式

  | 職涯方向 | 技能 | 產業公司 | 薪資 | 總分 | 說明 |
  | :-: | :-: | :-: | :-: | :-: | :--- |
  | 5 | 5 | 5 | 5 | 100 | |
  | 1 | 1 | 1 | 1 | 0 | |
  | 4 | 4 | 5 | 4 | 79 | |
  | 5 | 3 | `None` | `None` | 70 | 未知維度以 3 分代入 |
  | `None` | `None` | `None` | `None` | 50 | 全部未知，等同全部 3 分 |

- **驗證方式**：`uv run pytest tests/test_job_scoring_scorer.py -k compute_total`
- **通過條件**：全部 passed。

### AC-4：評分流程與 AI 回應處理（涵蓋 FR-2、FR-4、FR-5）

- **Given**：假的 LLM client，回傳 `career_fit` 5 分、`skill_match` 為 `null`、`industry_fit` 3 分、總評為 `總評`；另有一份 `career_fit` 與 `skill_match` 都是 `null` 的回應，以及一份 `career_fit` 為 6 分的回應
- **When**：分別對 `out` 與 `ok` 職缺呼叫 `score_job`，並驗證超出範圍的回應
- **Then**：
  - `out`：client 沒有被呼叫；結果為 `淘汰` true，`維度` 與 `總分` 都是 `None`
  - `ok`：client 被呼叫 1 次；`model_dump(by_alias=True)` 的鍵依序是四個中文維度名稱；`技能匹配度` 的分數為 `None`、`薪資水準` 為 4；`總分` 75；`未知維度` 為 `[技能匹配度]`；`評語` 為 `總評`
  - 兩個維度都是 `null` 的回應：`總分` 為 55；`未知維度` 為 `[職涯方向契合度, 技能匹配度]`；`評語` 維持 `總評`，不加任何前綴
  - 6 分的回應會讓 `AIAssessment.model_validate` 拋出 `ValidationError`
- **驗證方式**：`uv run pytest tests/test_job_scoring_scorer.py -k score_job`
- **通過條件**：全部 passed。

### AC-5：dry-run 印出提示詞且不建立 client（涵蓋 FR-6、FR-7）

- **Given**：已禁止建立 client
- **When**：以 `--dry-run` 對 `ok` 職缺呼叫 `main`
- **Then**：回傳 0；stdout 包含 `目標標記-AAA`、`經歷標記-BBB`、`工作標記-CCC` 與 `（無資料）`；禁止建立 client 的函式沒有被呼叫
- **驗證方式**：`uv run pytest tests/test_score_job_cli.py -k dry_run`
- **通過條件**：passed。

### AC-6：被淘汰的職缺不需要 API key（涵蓋 FR-2、FR-6）

- **Given**：已禁止建立 client
- **When**：不使用 dry-run，對 `out` 職缺呼叫 `main`
- **Then**：回傳 0；stdout 是 `淘汰` 為 true、`淘汰原因` 不為空的 JSON
- **驗證方式**：`uv run pytest tests/test_score_job_cli.py -k eliminated`
- **通過條件**：passed。

### AC-7：錯誤處理與供應商隔離（涵蓋 FR-6、FR-7）

- **Given**：`GEMINI_API_KEY` 設為空字串（`.env` 不會覆寫已存在的變數）
- **When**：
  - (a) 不使用 dry-run，對 `ok` 職缺呼叫 `main`
  - (b) 指定不存在的職缺代碼
  - (c) 以不存在的供應商呼叫 `get_client`
  - (d) 用 `ast` 掃描 `src/job_scoring/` 與 `src/score_job.py` 的 import
- **Then**：
  - (a) 回傳 1，stderr 含 `[-]` 與 `GEMINI_API_KEY`
  - (b) 回傳 1，stderr 含 `[-]`
  - (c) 拋出 `ValueError`
  - (d) 只有 `llm.py` import `google` 開頭的模組
- **驗證方式**：`uv run pytest tests/test_score_job_cli.py -k error`
- **通過條件**：全部 passed。

### AC-8：真實評分 〔需網路〕（涵蓋 FR-4、FR-5、FR-6）

- **Given**：已填寫 `profile/preferences.yaml` 與 `profile/experience.md`，已在 `.env` 設定 `GEMINI_API_KEY`，而且 `output/104/` 中有爬蟲結果；缺少任何一項時，測試顯示 skipped 並說明原因
- **When**：對最新一份結果中，第一筆有工作內容、而且沒被淘汰的職缺呼叫 `main`
- **Then**：
  - 輸出符合 [§7](../../spec/job-scoring.md#7-輸出jobscore)，四個維度依序出現
  - 每個維度都有非空的理由，分數是 1–5 或 `None`
  - 總分在 0–100 之間
  - 測試會印出完整結果（用 `-s` 顯示）
- **驗證方式**：`uv run pytest -m network -s tests/test_job_scoring_network.py -k real_scoring`
- **通過條件**：passed；使用者閱讀印出的理由，確認內容確實引用了職缺內容，而且與自己的判斷大致相符。

## 7. 待決問題

無。
