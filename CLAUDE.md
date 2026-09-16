# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。目前只有 104 職缺爬蟲有實作，其餘皆未動工。

## 常用指令

專案由 **uv** 管理，Python 3.14。

```bash
uv sync                      # 安裝依賴（含 dev group）
uv run main.py               # 目前仍是 uv 樣板，尚未成為真正進入點
uv run mypy 104/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
```

尚無測試框架與 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

| 想知道什麼 | 讀哪份 |
| :--- | :--- |
| 專案要做什麼、五項核心技術各自的實作現況、程式碼地圖、資料流 | [docs/spec/overview.md](docs/spec/overview.md) |
| 104 爬蟲的架構、請求標頭與頻率限制、職缺欄位字典、執行方式與輸出位置 | [docs/spec/104-scraper.md](docs/spec/104-scraper.md) |
| 程式碼風格、docstring 格式、終端輸出慣例、依賴管理、commit 規範 | [docs/spec/conventions.md](docs/spec/conventions.md) |

要新增功能時，先讀 overview.md 確認它對應到哪一項核心技術。
