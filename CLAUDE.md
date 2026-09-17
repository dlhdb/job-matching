# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。目前已實作 104 職缺爬蟲（F2-01）與單筆職缺評分（F1-01），其餘皆未動工。

## 常用指令

專案由 **uv** 管理，Python 3.14。

```bash
scripts/setup-dev-env.sh     # 建立開發環境：uv sync + 設定 nbstripout git filter（可重複執行）
uv sync                      # 只安裝依賴（含 dev group）
uv run src/main.py           # 目前仍是 uv 樣板，尚未成為真正進入點
uv run src/score_job.py --jobs output/104/<檔名>.json [--job-no <代碼>] [--dry-run]  # 單筆職缺評分
uv run pytest                # 離線測試（預設跳過需要網路的測試）
uv run pytest -m network     # 只跑需要網路的測試（會實際連線到外部服務）
uv run mypy src/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
```

尚無 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

| 想知道什麼 | 讀哪份 |
| :--- | :--- |
| 產品目標、用例、五項核心技術定義、功能清單與現況 | [docs/README.md](docs/README.md) |
| 單一功能的需求、範圍、設計、驗收標準 | `docs/features/F<編號>-*.md` |
| 撰寫新功能文件的格式 | [docs/feature_template.md](docs/feature_template.md) |
| 專案檔案結構 | [README.md](README.md) 的「專案結構」 |
| 模組間的資料流與輸入契約 | [docs/architecture.md](docs/architecture.md) |
| 104 爬蟲的請求標頭與頻率限制、職缺欄位字典、執行方式與輸出位置 | [docs/features/F2-01-104-job-scraper.md](docs/features/F2-01-104-job-scraper.md) |
| 工作評分的維度、淘汰與薪資規則、偏好檔格式、提示詞設計、輸出欄位、LLM 抽象層 | [docs/features/F1-01-job-scoring.md](docs/features/F1-01-job-scoring.md) |
| 程式碼風格、docstring 格式、文件撰寫規範（內容、格式、繪圖）、終端輸出慣例、依賴管理、測試慣例 | [docs/conventions.md](docs/conventions.md) |
| 隔離容器與防火牆白名單設計（所有 AI coding 工具共用） | [docs/ai-coding-setup/devcontainer.md](docs/ai-coding-setup/devcontainer.md) |
| Claude Code 專屬的權限規則（deny/ask）與設計理由 | [docs/ai-coding-setup/claude-code.md](docs/ai-coding-setup/claude-code.md) |

所有文件都描述系統的現況：需求、設計或實作改變時，直接更新對應的文件。一個功能的需求、設計與驗收標準都寫在同一份功能文件裡。撰寫或修改任何文件前，先讀 [docs/conventions.md](docs/conventions.md#文件撰寫) 的「文件撰寫」。

## 待辦事項

討論中出現、但確認不是現在要做的事（文件修正、延後的功能、後續改善），一律記到 [TODO.md](TODO.md)，不要順手處理。開始做某項時，再把它從 TODO.md 移除。

## 向使用者確認問題

需要使用者做決定時，不在對話中逐一詢問，改寫成問卷放在 `to-be-confirm/<主題>.md`，使用者填完後會通知你：

- 每題一個標題，寫出位置、問題與建議改法。位置與參考來源一律用相對於問卷的 markdown 超連結，指到行號（`[F1-01 第 63 行](../docs/features/F1-01-job-scoring.md#L63)`）或章節錨點，方便使用者跳轉查看。
- 選項用 `- [ ]` 列出，建議的選項標上「（建議）」，每題最後留一行「備註：」。
- 使用者通知填完後：
  - 讀取整份問卷再依答案處理，答案或備註不清楚時先問清楚再動手
  - 處理完就刪除該問卷，問卷不進版控

## 功能開發流程

1. 先讀 docs/README.md 確認功能對應哪一項核心技術，再讀該功能的文件。沒有功能文件，或功能文件仍有待決問題時，先與使用者釐清，不要直接實作。修改既有功能時，先在功能文件把新的 FR／AC 標上〔規劃中〕、狀態退回待規劃，與使用者確認後再實作。
2. 實作時只做「功能需求」列出的事，不碰「範圍外」。設計有調整時，同步更新功能文件的「設計」章節。
3. 完成後逐條執行功能文件的驗收標準，回報每條 ✅ / ❌ 與實際輸出；全部通過才移除〔規劃中〕標記，把功能文件與 docs/README.md 的狀態改為 ✅ 已完成，並更新 docs/README.md 中所屬核心技術的「現況」。
