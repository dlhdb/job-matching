# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。

## 常用指令

專案由 uv 管理，Python 3.14。

```bash
scripts/setup-dev-env.sh     # 建立開發環境：uv sync + npm ci + 設定 nbstripout git filter（可重複執行）
uv sync                      # 只安裝依賴（含 dev group）
uv run pytest                # 離線測試（預設跳過需要網路的測試）
uv run pytest -m network     # 只跑 tests/e2e 中連到外部服務的測試
uv run mypy src/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
uv run src/app.py            # 啟動網頁（127.0.0.1:8000），要先 build 前端
scripts/gen-api-types.sh     # 改了 API 後重新產生前端的 API 型別
```

前端在 `frontend/` 執行：

```bash
npm run build                # build 前端（uv run pytest 的瀏覽器測試會自動 build）
npm run dev                  # Vite 開發伺服器，/api 轉給 uv run src/app.py
npm test                     # Vitest
npm run typecheck            # 型別檢查
npm run lint                 # ESLint
npm run format               # Prettier 排版；npm run format:check 只檢查
npm install <pkg>            # 新增依賴（開發用加 -D）
```

前端用 ESLint 與 Prettier，Python 尚無 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

- 文件分區（產品／技術／慣例）與撰寫、使用流程：[docs/README.md](docs/README.md)
- 產品目標與成功指標、使用者問題、跨功能的使用者旅程、功能依賴、功能清單與現況、名詞定義：[docs/product/overview.md](docs/product/overview.md)
- 跨功能的模組依賴、資料存放位置與各資料表的負責功能、技術選型總覽：[docs/tech/architecture.md](docs/tech/architecture.md)
- 功能怎麼切、依賴方向、上層功能的需求動到底層時改哪一層的判斷方法：[docs/product/feature-design.md](docs/product/feature-design.md)
- 單一功能的為什麼做、做什麼（需求、範圍、業務規則、驗收標準、CLI 參數）：`docs/product/features/<功能 ID>.md`，功能 ID 見 overview 的功能清單
- 單一功能怎麼做（系統輪廓、模組分工、資料表、外部系統的技術限制、驗收對應的測試指令）：`docs/tech/tech-design/<功能 ID>.md`
- 功能文件、技術設計、決策紀錄的結構與各章寫法（〔規劃中〕、FR／AC 命名等）：[feature.md](docs/conventions/templates/feature.md)、[tech-design.md](docs/conventions/templates/tech-design.md)、[decision.md](docs/conventions/templates/decision.md)
- 專案檔案結構：[README.md](README.md) 的「專案結構」
- 所有文件共用的撰寫通則（文件分區、內容、決策紀錄什麼時候寫與放哪、格式）：[docs/conventions/documentation.md](docs/conventions/documentation.md)
- 程式碼風格、docstring 格式、終端輸出慣例、依賴管理、測試慣例、防禦性設計：[docs/conventions/development.md](docs/conventions/development.md)
- 過去的取捨、考慮過但不採用的做法與原因（決策紀錄，集中在 [docs/decisions/](docs/decisions/)，依性質分子目錄）：
  - 產品取捨：[docs/decisions/product/](docs/decisions/product/)
  - 技術取捨：[docs/decisions/tech/](docs/decisions/tech/)
  - 文件與開發流程的取捨：[docs/decisions/conventions/](docs/decisions/conventions/)
  - AI coding 工具的設定與只寫在 CLAUDE.md 的規則的取捨：[docs/decisions/ai-coding/](docs/decisions/ai-coding/)
- 隔離容器與防火牆白名單設計（所有 AI coding 工具共用）、Remote Control 要的網域與環境變數：[docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)
- Claude Code 專屬的權限規則（deny/ask）與設計理由：[docs/tech/ai-coding-setup/claude-code.md](docs/tech/ai-coding-setup/claude-code.md)
- AI coding 通用工作流（skill、hook，以及 skill 用到的 subagent）的說明與設計理由：`.claude/skills/<skill 名稱>/README.md`，例如 [commit-review](.claude/skills/commit-review/README.md)

產品文件（docs/product/）寫產品應有的樣子，規劃確定就更新；技術文件（docs/tech/）只寫已實作的現況，見 [documentation.md 的文件分區](docs/conventions/documentation.md#文件分區)。需求、設計或實作改變時，直接更新對應的文件。

撰寫或修改任何文件前：

- 先讀 [docs/conventions/documentation.md](docs/conventions/documentation.md)。
- 改的是功能文件、技術設計或決策紀錄時，再讀該類的範本。
- 只改文件時不必讀 development.md。

實作進度只記在 [docs/product/overview.md](docs/product/overview.md#功能清單) 的狀態與「現況」，本檔不記錄進度。

## 待辦事項

討論中出現、但確認不是現在要做的事（文件修正、延後的功能、後續改善、還沒決定做法的取捨），一律記到 [backlog/TODO.md](backlog/TODO.md)，不要順手處理。還沒決定要不要做的想法，寫得出要看什麼才能決定的，記在它的「待評估」。某項做完或決定不做時，才連同細節檔刪除，同時更新其他文件中連到該項的連結。各欄位與細節檔的寫法見 TODO.md 開頭。

## 向使用者確認問題

需要使用者做決定時（包括功能開發與 commit 審查），照 [ask-user](.claude/skills/ask-user/SKILL.md) skill 詢問。

## 先規劃再執行

符合下列任一條件的修改，先用 plan mode（EnterPlanMode）規劃，使用者核准後才動手，理由見[決策紀錄：具規模的修改先規劃再執行](docs/decisions/ai-coding/plan-before-large-changes.md)：

- 會改到兩個以上的檔案，或新增檔案（`to-be-confirm/` 的問卷與 `backlog/` 的 TODO.md、細節檔除外）
- 會改變行為、業務規則、資料表結構、CLI 參數或依賴
- 重整文件結構：拆章、合併、改名、搬移
- 做法不只一種合理選擇

不必規劃的例外，符合時優先於上面的條件：

- 錯字、單一檔案內不改變行為的小修正
- 使用者已明確指定改法的修改
- commit 審查的修正（見[功能開發流程](#功能開發流程)第 4 步）：需要使用者決定的修正照該 skill 詢問

不屬於任何例外、又不確定是否符合條件時，當作需要規劃。

## 功能開發流程

依 [docs/README.md 的撰寫與使用流程](docs/README.md#撰寫與使用流程)進行。無論是修改功能文件還是進行實作，都要遵守[先規劃再執行](#先規劃再執行)的規則。另外注意：

1. 讀文件時，功能文件只讀要動到的故事那章、它連到的規則，加上「非功能需求」與「共用規則」；技術設計讀「總覽」，再讀要動到的元件章節。
2. 沒有功能文件、功能文件仍有待決問題，或要修改既有功能時，先在功能文件規劃好並與使用者確認，再實作。
3. 驗收逐條回報 ✅ / ❌ 與實際輸出。
4. 每個 commit 都用 [commit-review](.claude/skills/commit-review/SKILL.md) skill 審查，只改文件的 commit 也要審查。
