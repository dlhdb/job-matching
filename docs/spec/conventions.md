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

## 終端輸出

以 emoji 前綴搭配狀態標記，維持既有風格：

- `[+]` 成功、`[-]` 失敗、`[!]` 警告、`[i]` 資訊
- 進度用 `⏳`、成果用 `🎉`、提示用 `💡`

## 依賴管理

專案由 **uv** 管理（`uv.lock`），Python 3.14。新增依賴走 `uv add` / `uv add --dev`，不要手改 `pyproject.toml` 之後跑 `pip`。

## Commit

規範定義在 [.claude/commands/commit.md](../../.claude/commands/commit.md)，要點：

- 繁體中文，首行 `<type>: <精簡摘要>`（Conventional Commits，摘要 ≤ 50 字元）
- 內文條列式，**第一項先說明這個改動的效益**，後續項目才描述做了什麼
- 產生後先顯示給使用者確認，不要直接 commit（除非明確要求）

## 防禦性設計

所有外部資料以 `.get()` 安全提取、對外請求一律設 `timeout`、缺值就是 `null`——**不自行腦補預設值或做 fallback 回填**。資料的真實性優先於欄位的完整度。
