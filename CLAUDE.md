# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。

## 常用指令

專案由 uv 管理，Python 3.14。

```bash
scripts/setup-dev-env.sh     # 建立開發環境：uv sync + 設定 nbstripout git filter（可重複執行）
uv sync                      # 只安裝依賴（含 dev group）
uv run pytest                # 離線測試（預設跳過需要網路的測試）
uv run pytest -m network     # 只跑需要網路的測試，都在 tests/e2e（會實際連線到外部服務）
uv run mypy src/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
```

尚無 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

- 文件分區（產品／技術／慣例）與撰寫、使用流程：[docs/README.md](docs/README.md)
- 產品目標與成功指標、使用者問題、跨功能的使用者旅程、功能清單與現況、名詞定義：[docs/product/overview.md](docs/product/overview.md)
- 跨功能的模組依賴、資料存放位置與各資料表的負責功能、技術選型總覽：[docs/tech/architecture.md](docs/tech/architecture.md)
- 單一功能的為什麼做、做什麼（需求、範圍、業務規則、驗收標準）：`docs/product/features/<功能 ID>.md`
- 單一功能怎麼做（系統輪廓、模組分工、資料表、外部系統的技術限制、驗收對應的測試指令）：`docs/tech/tech-design/<功能 ID>.md`
- 撰寫新功能文件、技術設計的格式：[docs/product/features/feature_template.md](docs/product/features/feature_template.md)、[docs/tech/tech-design/tech_design_template.md](docs/tech/tech-design/tech_design_template.md)
- 專案檔案結構：[README.md](README.md) 的「專案結構」
- 104 爬蟲的頻率限制、職缺欄位字典、執行方式與輸出位置：[docs/product/features/104-job-scraper.md](docs/product/features/104-job-scraper.md)
- 104 API 的請求標頭與限制、欄位來源、測試指令：[docs/tech/tech-design/104-job-scraper.md](docs/tech/tech-design/104-job-scraper.md)
- 職缺資料庫保存的資訊、跨次去重與出現時間的寫入規則、匯入既有 JSON 的指令：[docs/product/features/job-database.md](docs/product/features/job-database.md)
- 職缺資料庫的模組依賴、資料表 schema、測試指令：[docs/tech/tech-design/job-database.md](docs/tech/tech-design/job-database.md)
- 工作評分的維度、淘汰與薪資規則、偏好檔格式、提示詞內容、輸出欄位：[docs/product/features/job-scoring.md](docs/product/features/job-scoring.md)
- 工作評分的模組分工、`job_scores` 資料表、快取鍵計算、LLM 抽象層與 Gemini 的限制、測試指令：[docs/tech/tech-design/job-scoring.md](docs/tech/tech-design/job-scoring.md)
- MCP 介面的 tool 清單與參數、註冊方式：[docs/product/features/mcp-server.md](docs/product/features/mcp-server.md)
- MCP 介面尚未實作，暫定的技術方案（stdout 限制、資料表查詢）：[TODO.md](TODO.md#mcp-server-實作備忘)
- 文件撰寫規範（內容、功能文件與技術設計的結構、FR／AC 命名、決策紀錄、格式、繪圖）：[docs/conventions/documentation.md](docs/conventions/documentation.md)
- 程式碼風格、docstring 格式、終端輸出慣例、依賴管理、測試慣例、防禦性設計：[docs/conventions/development.md](docs/conventions/development.md)
- 過去的取捨、考慮過但不採用的做法與原因（決策紀錄，依性質分三處）：
  - 產品取捨：[docs/product/decisions/](docs/product/decisions/)
  - 技術取捨：[docs/tech/decisions/](docs/tech/decisions/)
  - 文件與開發流程的取捨：[docs/conventions/decisions/](docs/conventions/decisions/)
- 隔離容器與防火牆白名單設計（所有 AI coding 工具共用）、Remote Control 要的網域與環境變數：[docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)
- Claude Code 專屬的權限規則（deny/ask）與設計理由：[docs/tech/ai-coding-setup/claude-code.md](docs/tech/ai-coding-setup/claude-code.md)

所有文件都描述系統的現況：需求、設計或實作改變時，直接更新對應的文件。一個功能的需求、業務規則與驗收標準寫在功能文件，實作方式寫在技術設計。撰寫或修改任何文件前，先讀 [docs/conventions/documentation.md](docs/conventions/documentation.md)。只改文件時不必讀 development.md。

實作進度只記在 [docs/product/overview.md](docs/product/overview.md#功能清單) 的狀態與「現況」，本檔不記錄進度。

## 待辦事項

討論中出現、但確認不是現在要做的事（文件修正、延後的功能、後續改善），一律記到 [TODO.md](TODO.md)，不要順手處理。開始做某項時，再把它從 TODO.md 移除。

## 向使用者確認問題

需要使用者做決定時，不在對話中逐一詢問，改寫成問卷放在 `to-be-confirm/<主題>.md`，使用者填完後會通知你：

- 每題一個標題，寫出位置、問題與建議改法。位置與參考來源一律用相對於問卷的 markdown 超連結，指到行號（`[job-scoring 第 63 行](../docs/product/features/job-scoring.md#L63)`）或章節錨點，方便使用者跳轉查看。
- 選項用 `- [ ]` 列出，建議的選項標上「（建議）」，每題最後留一行「備註：」。
- 使用者通知填完後：
  - 讀取整份問卷再依答案處理，答案或備註不清楚時先問清楚再動手
  - 處理完就刪除該問卷，問卷不進版控

## 功能開發流程

1. 先在 docs/product/overview.md 的功能清單找到要做的功能，再讀該功能的文件：
   - 功能文件以「使用者故事」為章節，一個故事自己帶著需求、規則與驗收（結構規則見 [docs/conventions/documentation.md](docs/conventions/documentation.md#功能文件的結構)），所以只需要讀要動到的故事那章、它連到的規則，加上「非功能需求」與「共用規則」。
   - 技術設計讀「總覽」掌握系統輪廓，再讀要動到的元件章節。
   - 沒有功能文件，或功能文件仍有待決問題時，先與使用者釐清，不要直接實作。
   - 修改既有功能時，先在功能文件把新增或修改的使用者故事標上〔規劃中〕、狀態退回待規劃，與使用者確認後再實作。
2. 實作時只做該使用者故事「需求」列出的事，不碰「範圍外」。業務規則有調整時，同步更新該故事的「規則」小節。技術方案寫在實作計畫或 commit 說明，不寫進技術設計。
3. 完成後依技術設計的「驗收對照」，逐條執行該使用者故事的每一條驗收，回報 ✅ / ❌ 與實際輸出。全部通過後：
   - 移除〔規劃中〕標記，把功能文件與 docs/product/overview.md 的狀態改為 ✅ 已完成，並更新 docs/product/overview.md 中該功能的「現況」。
   - 把會長期留下的設計更新到技術設計對應的元件章節，並在驗收對照補上新的 AC。
