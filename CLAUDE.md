# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

「求職雷達」：自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，避免人工在海量職缺中過濾。

## 常用指令

專案由 uv 管理，Python 3.14。

```bash
scripts/setup-dev-env.sh     # 建立開發環境：uv sync + 設定 nbstripout git filter（可重複執行）
uv sync                      # 只安裝依賴（含 dev group）
uv run pytest                # 離線測試（預設跳過需要網路的測試）
uv run pytest -m network     # 只跑 tests/e2e 中連到外部服務的測試
uv run mypy src/             # 型別檢查（mypy 已列為 dev 依賴，但尚無設定檔）
uv add <pkg>                 # 新增依賴
```

尚無 lint 設定。

## 文件索引

需要下列資訊時，再去讀對應的文件：

- 文件分區（產品／技術／慣例）與撰寫、使用流程：[docs/README.md](docs/README.md)
- 產品目標與成功指標、使用者問題、跨功能的使用者旅程、功能依賴、功能清單與現況、名詞定義：[docs/product/overview.md](docs/product/overview.md)
- 跨功能的模組依賴、資料存放位置與各資料表的負責功能、技術選型總覽：[docs/tech/architecture.md](docs/tech/architecture.md)
- 單一功能的為什麼做、做什麼（需求、範圍、業務規則、驗收標準、CLI 參數）：`docs/product/features/<功能 ID>.md`，功能 ID 見 overview 的功能清單
- 單一功能怎麼做（系統輪廓、模組分工、資料表、外部系統的技術限制、驗收對應的測試指令）：`docs/tech/tech-design/<功能 ID>.md`
- 功能文件、技術設計各章的寫法：[docs/product/features/_feature_template.md](docs/product/features/_feature_template.md)、[docs/tech/tech-design/_tech_design_template.md](docs/tech/tech-design/_tech_design_template.md)
- 專案檔案結構：[README.md](README.md) 的「專案結構」
- 文件撰寫規範（跨文件的規則、〔規劃中〕、FR／AC 命名、決策紀錄、格式）：[docs/conventions/documentation.md](docs/conventions/documentation.md)
- 程式碼風格、docstring 格式、終端輸出慣例、依賴管理、測試慣例、防禦性設計：[docs/conventions/development.md](docs/conventions/development.md)
- 過去的取捨、考慮過但不採用的做法與原因（決策紀錄，依性質分三處）：
  - 產品取捨：[docs/product/decisions/](docs/product/decisions/)
  - 技術取捨：[docs/tech/decisions/](docs/tech/decisions/)
  - 文件與開發流程的取捨：[docs/conventions/decisions/](docs/conventions/decisions/)
- 隔離容器與防火牆白名單設計（所有 AI coding 工具共用）、Remote Control 要的網域與環境變數：[docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)
- Claude Code 專屬的權限規則（deny/ask）與設計理由：[docs/tech/ai-coding-setup/claude-code.md](docs/tech/ai-coding-setup/claude-code.md)

產品文件（docs/product/）寫產品應有的樣子，規劃確定就更新；技術文件（docs/tech/）只寫已實作的現況，見 [documentation.md 的文件分區](docs/conventions/documentation.md#文件分區)。需求、設計或實作改變時，直接更新對應的文件。撰寫或修改任何文件前，先讀 [docs/conventions/documentation.md](docs/conventions/documentation.md)，只改文件時不必讀 development.md。

實作進度只記在 [docs/product/overview.md](docs/product/overview.md#功能清單) 的狀態與「現況」，本檔不記錄進度。

## 待辦事項

討論中出現、但確認不是現在要做的事（文件修正、延後的功能、後續改善），一律記到 [TODO.md](TODO.md)，不要順手處理。開始做某項時，再把它從 TODO.md 移除。

## 向使用者確認問題

需要使用者做決定時（包括功能開發與 commit 前審查），依問題的複雜度選擇詢問方式：

- 選項少、不需要太多脈絡說明：直接在對話中問。
- 需要較多脈絡說明，或題數多：寫成問卷放在 `to-be-confirm/<主題>.md`，使用者填完後會通知你。問卷不進版控。
  - 每題一個標題，寫出位置、問題與建議改法。位置與參考來源用相對於問卷的連結，指到行號（`[job-auto-scoring 第 63 行](../docs/product/features/job-auto-scoring.md#L63)`）或章節錨點。
  - 選項用 `- [ ]` 列出，建議的選項標上「（建議）」，每題最後留一行「備註：」。
  - 收到通知後讀完整份問卷再處理，答案或備註不清楚時先問清楚，處理完就刪除問卷。

## 先規劃再執行

符合下列任一條件的修改，先用 plan mode（EnterPlanMode）規劃，使用者核准後才動手，理由見[決策紀錄：具規模的修改先規劃再執行](docs/conventions/decisions/plan-before-large-changes.md)：

- 會改到兩個以上的檔案，或新增檔案（`to-be-confirm/` 的問卷與 TODO.md 除外）
- 會改變行為、業務規則、資料表結構、CLI 參數或依賴
- 重整文件結構：拆章、合併、改名、搬移
- 做法不只一種合理選擇

不必規劃的例外，符合時優先於上面的條件：

- 錯字、單一檔案內不改變行為的小修正
- 使用者已明確指定改法的修改
- commit 前審查的修正（見[功能開發流程](#功能開發流程)第 4 步）：需要使用者決定的修正照該步驟詢問

不屬於任何例外、又不確定是否符合條件時，當作需要規劃。

## 功能開發流程

依 [docs/README.md 的撰寫與使用流程](docs/README.md#撰寫與使用流程)進行。無論是修改功能文件還是進行實作，都要遵守[先規劃再執行](#先規劃再執行)的規則。另外注意：

1. 讀文件時，功能文件只讀要動到的故事那章、它連到的規則，加上「非功能需求」與「共用規則」；技術設計讀「總覽」，再讀要動到的元件章節。
2. 沒有功能文件、功能文件仍有待決問題，或要修改既有功能時，先在功能文件規劃好並與使用者確認，再實作。
3. 驗收逐條回報 ✅ / ❌ 與實際輸出。
4. commit 前先審查修改，只改文件的 commit 也要審查：
   - 用獨立的指令 `git add` 要 commit 的檔案，再執行 `/code-review medium`。
   - 修正發現的問題並重跑測試，有改動就重新暫存，再審查一次，直到除了已向使用者說明、決定不修的問題以外，沒有其他問題為止。
   - 修正需要使用者決定時（例如要改業務規則、需求或驗收，或有多種合理修法），先停下來依「向使用者確認問題」詢問，不自行選一種修法。
   - 修正最多三輪：第三輪修正後的審查仍有上述以外的問題時，停下來向使用者說明剩下的問題並詢問怎麼處理，不再自行修改，也不 commit。
   - 暫存區定案後執行 `.claude/hooks/require-review.sh --mark`，再單獨執行 `git commit`（不用 `-a`）。沒有 `--mark`，或 `--mark` 之後暫存區又有變動，commit 會被 PreToolUse hook 擋下。
