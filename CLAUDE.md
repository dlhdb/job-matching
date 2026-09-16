# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。目前只有 104 職缺爬蟲有實作，其餘皆未動工。

## 常用指令

專案由 **uv** 管理，Python 3.14。

```bash
uv sync                      # 安裝依賴（含 dev group）
uv run src/main.py           # 目前仍是 uv 樣板，尚未成為真正進入點
uv run mypy src/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
```

尚無測試框架與 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

| 想知道什麼 | 讀哪份 |
| :--- | :--- |
| 產品目標、用例、五項核心技術定義、功能清單與狀態 | [docs/prd/README.md](docs/prd/README.md) |
| 單一功能的需求、範圍、驗收標準 | `docs/prd/features/F<編號>-*.md` |
| 撰寫新 PRD 的格式 | [docs/prd/_template.md](docs/prd/_template.md) |
| 專案檔案結構 | [README.md](README.md) 的「專案結構」 |
| 模組間的資料流與輸入契約 | [docs/spec/architecture.md](docs/spec/architecture.md) |
| 104 爬蟲的架構、請求標頭與頻率限制、職缺欄位字典、執行方式與輸出位置 | [docs/spec/104-scraper.md](docs/spec/104-scraper.md) |
| 程式碼風格、docstring 格式、終端輸出慣例、依賴管理 | [docs/spec/conventions.md](docs/spec/conventions.md) |

`docs/spec/` 寫「怎麼做」，`docs/prd/` 寫「要做什麼、做到哪算完成」。

## 功能開發流程

1. 先讀 docs/prd/README.md 確認功能對應哪一項核心技術，再讀該功能的 PRD。沒有 PRD 或 PRD 仍有待決問題時，先與使用者釐清，不要直接實作。
2. 實作時只做「功能需求」列出的事，不碰「範圍外」。
3. 完成後逐條執行 PRD 的驗收標準，回報每條 ✅ / ❌ 與實際輸出；全部通過才把 PRD 與 PRD 索引的狀態改為已完成。
