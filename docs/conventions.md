# 開發慣例

## 語言

程式碼註解、docstring、終端輸出、文件一律使用**繁體中文**。

docstring 沿用既有的 reStructuredText 風格：

```python
def resolve_area(area_input):
    """
    將使用者輸入的地區名稱解析為 (area_code, area_label)。

    :param area_input: str or None, 使用者輸入的地區名稱
    :return: tuple (str or None, str), (地區代碼, 顯示用地區名稱)
    """
```

## 文件撰寫

### 內容

- 文件描述系統的現況，不寫討論或決策過程（例如「已與使用者確認…」）。決策的結果寫進對應的範圍、需求或設計。
- 只寫程式碼講不出來的事：規則與理由、外部系統的限制、資料契約。不抄寫函式簽名、完整的 API 呼叫，或逐行翻譯程式碼。
- 尚未實作的內容要明確標示（功能文件用〔規劃中〕，流程見 [docs/README.md](README.md#撰寫與使用流程)），不把願景寫成現況。
- 具體優於抽象：寫出真實的欄位名、檔名、數值，不用「智慧」「高效」這類形容詞。

### 格式

- 不同的概念、決策或情況用條列分開，不用「；」串在同一句。
- 粗體只用在真正需要跳出來的地方，程式碼識別字用反引號就好。
- 引用其他文件時用 markdown 超連結，盡量指到章節錨點。
- 流程圖、架構圖、時序圖等一律用 **mermaid** 繪製，不用 ASCII 字元畫圖。節點文字含括號、冒號等符號時，用雙引號包起來（`A["文字 (說明)"]`），避免解析失敗。目錄結構清單不算圖，維持純文字區塊。
- 線性流程用編號清單，不畫圖。流程包含迴圈、判斷、分支等邏輯時，才用圖來表達。

### 程式碼與文件的關係

程式碼（含註解、docstring、測試、範本檔）不引用文件的檔名、章節或編號（功能 ID、FR、AC）。文件的位置由 CLAUDE.md 與 README.md 的索引負責，文件重整時才不必跟著改程式碼。

## 終端輸出

以 emoji 前綴搭配狀態標記，維持既有風格：

- `[+]` 成功、`[-]` 失敗、`[!]` 警告、`[i]` 資訊
- 進度用 `⏳`、成果用 `🎉`、提示用 `💡`

## 依賴管理

專案由 **uv** 管理（`uv.lock`），Python 3.14。新增依賴走 `uv add` / `uv add --dev`，不要手改 `pyproject.toml` 之後跑 `pip`。

## 測試

使用 **pytest**，設定在 `pyproject.toml` 的 `[tool.pytest]`。

```bash
uv run pytest                        # 離線測試（預設跳過 network 標記）
uv run pytest -m network tests/e2e   # 連到真實外部服務的測試
```

測試只依「是否連到外部服務」分成兩處：

- `tests/test_<模組>.py`：離線測試，每個模組一個檔案。不區分單元測試與整合測試，同一個檔案可以同時測單一函式和從程式入口跑完的流程。
- `tests/e2e/test_<模組>.py`：連到真實外部服務（104、Gemini）的測試，加上 `@pytest.mark.network`。

兩處都不加 `__init__.py`。兩處可以有同名檔案，因為 pytest 設定了 `--import-mode=importlib`，代價是測試檔之間不能互相 import。

- 共用 fixture 放在 `tests/conftest.py`。只有單一檔案會用到的 helper 留在該檔案裡。
- `src/` 已經加入 import 路徑，直接 `import fetch_104_jobs`，不用 importlib 載入。
- **只換外部依賴**：離線測試用 `monkeypatch` 把 `requests.get`、LLM client 等外部呼叫換成假函式，專案內的函式照常執行，重構時測試才不會跟著壞。只有準備假資料的成本明顯過高時，才換掉專案內的函式，例如測 `main` 的參數解析時換掉 `execute_scraping`。
- `time.sleep` 用 `no_sleep` fixture 取代，這個 fixture 也會記錄延遲秒數，方便驗證頻率限制。
- **測試資料固定不變**：測試不讀 `profile/`、`output/` 這類會變動的專案資料。離線測試的資料寫在測試碼裡，需要檔案時寫到 `tmp_path`；e2e 的輸入資料放在 `tests/e2e/data/`。範本檔（`*.example.*`）只在驗證範本本身的測試中讀取。
- `tests/e2e/` 的測試缺少 API key 等前提時，用 `pytest.skip` 說明原因，不要讓測試失敗。
- 檔案一律寫到 `tmp_path`。會寫入 `output/` 的程式，用 monkeypatch 把輸出目錄改掉，不要污染真實資料。
- 需要多組輸入時，用 `@pytest.mark.parametrize`。功能文件驗收標準中的「輸入 → 預期」表格，就直接對應到這裡的參數。
- 測試函式名稱以被測的函式名稱開頭（例如 `test_parse_keywords_*`），讓驗收標準可以用 `-k <函式名>` 挑出對應的測試。
- CLI 進入點提供 `main(argv) -> int`，測試直接呼叫並用 `capsys` 檢查輸出；只有訊號處理這類必須在真實行程中驗證的行為，才用 subprocess。

## 防禦性設計

所有外部資料以 `.get()` 安全提取、對外請求一律設 `timeout`、缺值就是 `null`——**不自行腦補預設值或做 fallback 回填**。資料的真實性優先於欄位的完整度。
