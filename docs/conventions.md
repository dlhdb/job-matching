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

文件中的流程圖、架構圖、時序圖等一律用 **mermaid** 繪製，不用 ASCII 字元畫圖。節點文字含括號、冒號等符號時，用雙引號包起來（`A["文字 (說明)"]`），避免解析失敗。目錄結構清單不算圖，維持純文字區塊。

## 終端輸出

以 emoji 前綴搭配狀態標記，維持既有風格：

- `[+]` 成功、`[-]` 失敗、`[!]` 警告、`[i]` 資訊
- 進度用 `⏳`、成果用 `🎉`、提示用 `💡`

## 依賴管理

專案由 **uv** 管理（`uv.lock`），Python 3.14。新增依賴走 `uv add` / `uv add --dev`，不要手改 `pyproject.toml` 之後跑 `pip`。

## 測試

使用 **pytest**，設定在 `pyproject.toml` 的 `[tool.pytest]`。

```bash
uv run pytest               # 離線測試（預設跳過 network 標記）
uv run pytest -m network    # 只跑需要網路的測試
```

- 測試放在 `tests/test_<模組>.py`，採平面結構，不加 `__init__.py`；共用 fixture 放在 `tests/conftest.py`。
- `src/` 已經加入 import 路徑，直接 `import fetch_104_jobs`，不用 importlib 載入。
- **預設離線**：HTTP 請求、LLM client 等外部呼叫一律用 `monkeypatch` 換成假函式。`time.sleep` 用 `no_sleep` fixture 取代，這個 fixture 也會記錄延遲秒數，方便驗證頻率限制。
- 需要連線到外部服務的測試，加上 `@pytest.mark.network`。缺少 API key 或輸入資料等前提時，用 `pytest.skip` 說明原因，不要讓測試失敗。
- 檔案一律寫到 `tmp_path`。會寫入 `output/` 的程式，用 monkeypatch 把輸出目錄改掉，不要污染真實資料。
- 需要多組輸入時，用 `@pytest.mark.parametrize`。功能文件驗收標準中的「輸入 → 預期」表格，就直接對應到這裡的參數。
- 測試函式名稱以被測的函式名稱開頭（例如 `test_parse_keywords_*`），讓驗收標準可以用 `-k <函式名>` 挑出對應的測試。
- CLI 進入點提供 `main(argv) -> int`，測試直接呼叫並用 `capsys` 檢查輸出；只有訊號處理這類必須在真實行程中驗證的行為，才用 subprocess。

## 防禦性設計

所有外部資料以 `.get()` 安全提取、對外請求一律設 `timeout`、缺值就是 `null`——**不自行腦補預設值或做 fallback 回填**。資料的真實性優先於欄位的完整度。
