# 開發慣例

寫程式碼、測試或調整依賴時讀這份。文件的撰寫慣例見 [documentation.md](documentation.md)。

## 語言

程式碼註解、docstring、終端輸出一律使用繁體中文。

docstring 沿用既有的 reStructuredText 風格：

```python
def resolve_area(area_input):
    """
    將使用者輸入的地區名稱解析為 (area_code, area_label)。

    :param area_input: str or None, 使用者輸入的地區名稱
    :return: tuple (str or None, str), (地區代碼, 顯示用地區名稱)
    """
```

TypeScript 的說明用 `/** */`（JSDoc）：

- 只寫用途與規則，不重複型別：型別已經寫在程式碼裡。

## 程式碼與文件的關係

程式碼（含註解、docstring、測試、範本檔）不引用文件的檔名、章節或編號（功能 ID、FR、AC）。文件的位置由 CLAUDE.md 與 README.md 的索引負責，搬移、改名或重新編排文件時才不必改程式碼。

## 終端輸出

以 emoji 前綴搭配狀態標記，維持既有風格：

- `[+]` 成功、`[-]` 失敗、`[!]` 警告、`[i]` 資訊
- 進度用 `⏳`、成果用 `🎉`、提示用 `💡`

## 依賴管理

- Python：新增依賴走 `uv add` / `uv add --dev`，不要手改 `pyproject.toml` 之後跑 `pip`。
- 前端：在 `frontend/` 以 `npm install <套件>` 新增，開發用的加 `-D`。
  - `package-lock.json` 進版控，照它安裝用 `npm ci`（`scripts/setup-dev-env.sh` 會執行）。
  - 容器內的 `frontend/node_modules` 是 Docker volume，不和主機共用，見 [devcontainer.md](../tech/ai-coding-setup/devcontainer.md#虛擬環境前端依賴與-git-設定)。

## 前端的 lint 與格式

- ESLint 管寫法（TypeScript 與 React hooks 的建議規則），Prettier 管格式（`printWidth` 100，其餘用預設）。
  - `eslint-config-prettier` 關掉 ESLint 裡和 Prettier 衝突的規則，兩者不重疊。
- commit 前在 `frontend/` 執行 `npm run lint` 與 `npm run format:check`，都要通過。
  - `npm run format` 自動排版。
- 產出檔不排版也不 lint：`dist/`、`package-lock.json`、`openapi.json`、`src/api/schema.d.ts`。
- Python 目前沒有 lint 與格式工具。

## API 型別

後端的回應模型是前後端欄位的唯一來源，前端不手寫 API 的型別：

- `scripts/gen-api-types.sh` 從 FastAPI 的 OpenAPI 產生 `frontend/openapi.json`，再以 `openapi-typescript` 轉成 `frontend/src/api/schema.d.ts`。
  - 兩個都是產出檔，進版控、不手改。
- 改了 API 的路徑或回應模型後執行這支腳本。
  - `tests/test_web_openapi.py` 比對 `openapi.json`，沒有更新時失敗。
- 端點明寫 `summary` 與 `description`：沒寫時 FastAPI 會把整段 docstring（含 `:param`）放進 OpenAPI 與前端的型別註解。

## 測試

使用 pytest，設定在 `pyproject.toml` 的 `[tool.pytest]`，執行指令見 CLAUDE.md。測試只依「是否連到外部服務」分成兩處：

- `tests/test_<模組>.py`：離線測試，每個模組一個檔案，不區分單元測試與整合測試。
- `tests/e2e/test_<模組>.py`：連到真實外部服務（104、Gemini）的測試，加上 `@pytest.mark.network`。缺少 API key 等前提時，用 `pytest.skip` 說明原因，不要讓測試失敗。
- 兩處都不加 `__init__.py`，可以有同名檔案（`--import-mode=importlib`），代價是測試檔之間不能互相 import。

前端的規則用 Vitest 測，是「測試放在 `tests/`」的例外：

- 測試檔 `<模組>.test.ts` 放在原始碼旁邊，例如 `frontend/src/job-database/sort.test.ts`，Vite、TypeScript 與 ESLint 的設定都以 `frontend/src/` 為範圍。
- 執行：`npm test --prefix frontend`。
  - 只跑部分檔案時在後面加檔名的一部分，例如 `npm test --prefix frontend -- sort`。
- 以 `describe` 標出被測的函式名稱。
- 功能文件驗收中的「輸入 → 預期」用 `it.each` 對應成參數。
- 只測純函式，元件的行為交給瀏覽器測試。

撰寫規則：

- `src/` 已經加入 import 路徑，直接 `import fetch_104_jobs`，不用 importlib 載入。
- 共用 fixture 放在 `tests/conftest.py`，只有單一檔案會用到的 helper 留在該檔案裡。
- 只換外部依賴：
  - 離線測試用 `monkeypatch` 把 `requests.get`、LLM client 等外部呼叫換成假函式，專案內的函式照常執行，重構時測試才不會跟著壞。
  - 只有準備假資料的成本明顯過高時，才換掉專案內的函式，例如確認不會呼叫 AI 時換掉評分 CLI 的 `get_client`。
  - 爬蟲請求之間的延遲用 `no_sleep` fixture 取代，它也會記錄延遲秒數，方便驗證頻率限制。
- 測試資料固定不變：
  - 不讀 `profile/`、`output/` 這類會變動的專案資料。範本檔（`*.example.*`）只在驗證範本本身的測試中讀取。
  - 離線測試的資料寫在測試碼裡，e2e 的輸入資料放在 `tests/e2e/data/`。
- 檔案一律寫到 `tmp_path`。會寫入 `output/` 的程式，用 monkeypatch 把輸出目錄改掉。
  - 例外：e2e 測試中要讓使用者跑完直接打開查看的檔案，寫到 `output/e2e/`（不進版控），每次執行前刪除上次留下的檔案，跑完保留。
- 測試函式名稱以被測的函式名稱開頭（例如 `test_parse_keywords_*`），技術設計的驗收對照才能用 `-k <函式名>` 挑出對應的測試。
- 功能文件驗收中逐項列出的「輸入 → 預期」，用 `@pytest.mark.parametrize` 對應成參數。
- CLI 進入點提供 `main(argv) -> int`，測試直接呼叫並用 `capsys` 檢查輸出。只有訊號處理這類必須在真實行程中驗證的行為，才用 subprocess。

### 瀏覽器測試

網頁的行為以 Playwright（`pytest-playwright`）操作真的 Chromium 驗證，前後端串起來測：

- 檔名是 `tests/test_browser_<頁面>.py`，函式名稱以頁面開頭，例如 `test_job_table_sort`。
- 用 `live_server` fixture 起伺服器：
  - 在測試行程的執行緒中執行。
  - 資料庫是 `tmp_path` 下的測試資料庫。
  - 外部服務一樣可以用 `monkeypatch` 換掉。
- 第一個瀏覽器測試開始前，自動執行一次 `npm run build`，測的一定是目前的前端，不會拿改之前的舊 build。
  - build 失敗時瀏覽器測試失敗，並附上 build 的輸出。
- 使用容器內以 apt 安裝的 Chromium，不執行 `playwright install`，理由見 [devcontainer.md](../tech/ai-coding-setup/devcontainer.md#容器內的工具)。
- 找不到 Chromium（例如在主機上執行）、找不到 npm 或還沒安裝前端依賴時，`pytest.skip` 並說明原因。
  - 在容器內驗收時，瀏覽器測試不能被 skip。
- 頁面上連到外部網站的連結，以 `page.context.route` 攔下請求，不真的連出去。

## 防禦性設計

資料的真實性優先於欄位的完整度：

- 所有外部資料以 `.get()` 安全提取。
- 對外請求一律設 `timeout`。
- 缺值就是 `null`，**不自行腦補預設值或做 fallback 回填**。
