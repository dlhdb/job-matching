# 求職雷達（job-matching-agent）

自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，過濾出符合自我發展方向的職缺。

## 解決什麼問題

- 避免花大量精力在海量求職平台中人工過濾職缺。
- 了解不同產業、公司現在的發展方向。

## 快速開始

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.14，網頁的前端另外需要 [Node.js](https://nodejs.org/)。第一次使用先執行設定腳本：

```bash
scripts/setup-dev-env.sh
```

腳本會做三件事，可以重複執行：

- 安裝依賴（`uv sync`）。
- 安裝前端依賴（`npm ci`）；沒有 Node.js 時略過，其他步驟照常完成。
- 設定 git filter，`git add` 時自動移除 notebook 的輸出，避免職缺資料進版控。

每次重新 clone 都要再執行一次：

- filter 設定存在 `.git/config`，不會跟著 clone 下來。
- 沒設定時 `git add` 不會有任何警告，notebook 的輸出會直接進版控。

使用 devcontainer 時，建立容器會自動執行這支腳本。

### 我想抓 104 的職缺

1. build 前端，再啟動網頁：

   ```bash
   npm run build --prefix frontend
   uv run src/app.py
   ```

2. 用瀏覽器打開 `http://127.0.0.1:8000`，切到「抓取」。devcontainer 內 VS Code 會自動轉發 port。
3. 填條件後按「開始抓取」：
   - 關鍵字：多個用逗號分隔，重複的職缺會自動合併。
   - 縣市：不選代表全台灣。
   - 每個關鍵字抓幾頁（每頁 30 筆）與職缺性質。
   - 抓取在背景跑，重新整理或關掉頁面都不會中斷，回來時接回進度。
   - 可以按「停止」，已取完內容的職缺照樣列出。
4. 抓完先預覽，標「新」的是資料庫裡還沒有的職缺。整批按「存入職缺資料庫」或「捨棄」。
   - 存入後會打開職缺表，只列出剛存入的職缺。
   - 條件會記在瀏覽器，下次打開抓取頁時沿用。

### 我想瀏覽或分析累積下來的職缺

- 在網頁的「職缺表」選欄位、排序、篩選，點一列看完整的工作內容。
- 職缺存在 `data/jobs.db`（SQLite）：
  - 同一筆職缺只保留一列，並記錄第一次與最後一次被抓到的時間。
  - 每次存入都記下這次的搜尋條件。
- 各欄位的意義見 [job-database §8.2.1 職缺欄位契約](docs/product/features/job-database.md#821-職缺欄位契約)。
- 想自己分析時，用 `pandas.read_sql` 或任何 SQLite 工具讀取即可：
  - 保存的資訊見 [job-database §8.2.2](docs/product/features/job-database.md#822-保存的資訊)。
  - 資料表 schema 見 [job-database 技術設計](docs/tech/tech-design/job-database.md#32-資料表)。

### 我想讓 AI 幫我評估職缺適不適合

1. 在網頁的「設定」填入自己的偏好與經歷：
   - 偏好（YAML）：想做的方向、偏好的產業、期望與底線月薪、直接淘汰的公司與職稱關鍵字、各維度的權重。
   - 經歷（自由格式）：工作經歷與技能，全文會放進送給 AI 的提示詞。
   - 一開始是專案附的預設範例。
   - 改好後按「儲存並套用」，填名稱存成一個版本。
   - 之後可以隨時套用任何一版。
   - 提示詞模板也可以在這裡改。
2. 在 `.env` 填入 [Gemini API key](https://aistudio.google.com/apikey)：

   ```bash
   cp .env.example .env
   ```

- 在職缺表勾選職缺送去評分的介面還在製作中，目前還不能開始評分。
- 評分會依職涯方向、技能、產業公司、薪資四個維度給出 0–100 總分與理由。
- 薪資太低、公司或職稱在排除清單中的職缺直接淘汰，不呼叫 AI。
- 評分方式見 [job-auto-scoring 自動評分並看懂每個分數](docs/product/features/job-auto-scoring.md#4-自動評分並看懂每個分數score)。
- 從舊版升級時：
  - 啟動網頁會自動把資料庫改成新版，並把改版前的備份留在 `data/`。
  - 以前放在 `profile/` 的偏好與經歷不會自動讀進來，要自己貼進設定頁。

## 在隔離環境中讓 Coding Agent 自主執行

[.devcontainer/](.devcontainer/) 提供一個 Docker 容器，讓 AI coding agent（目前設定的是 Claude Code）可以不經逐步確認直接執行：

- 容器內的指令不會碰到主機。
- 對外連線只允許必要的網域。

設計細節見 [docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)。

1. 安裝 Docker Desktop 與 VS Code 的 [Dev Containers 擴充套件](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)，並啟動 Docker Desktop。
2. 在 VS Code 執行 「Dev Containers: Reopen in Container」。第一次建置會：
   - 安裝 Python 3.14 與 Claude Code
   - 執行 `scripts/setup-dev-env.sh`
3. 在容器的終端機執行：

   ```bash
   claude --dangerously-skip-permissions
   ```

   也可以使用 Claude Code 擴充套件，在模式選單選 「Bypass permissions」。

注意事項：

- 專案資料夾是直接掛載進容器的，agent 的修改會直接出現在主機上。
  - 建議在獨立分支上工作。
- 容器內看得到 `.env`，AI API key 建議設定用量上限。
- 允許清單是在容器啟動時把網域解析成 IP。
  - 如果某個服務的 IP 變了而連不上，執行 `sudo /usr/local/bin/init-firewall.sh` 重新套用。
- 需要新的網域時，編輯 [init-firewall.sh](.devcontainer/init-firewall.sh) 的 `ALLOWED_DOMAINS`，然後重建容器。

## 專案結構

```
src/            程式碼：爬蟲、職缺資料庫、評分邏輯、網頁的後端
frontend/       網頁的前端（React + TypeScript + Vite）
tests/          測試
notebooks/      分析資料的 Jupyter notebook
scripts/        工具腳本
prototypes/     介面原型（假資料，確認介面用）
output/         應用程式輸出結果（不進版控）
data/           職缺資料庫 jobs.db 與改版前的備份（不進版控）
backlog/        待辦與想法：TODO.md 是索引，tasks/、ideas/ 放長的細節
docs/           文件：product/（產品）、tech/（技術）、conventions/（慣例）、decisions/（決策紀錄）
.devcontainer/  開發環境隔離容器設定
```

## 文件導覽

文件依讀者分成產品、技術與慣例三區，決策紀錄另外集中在一處。完整索引與撰寫流程見 [docs/README.md](docs/README.md)。

- 產品（為什麼做、做什麼）：
  - [docs/product/overview.md](docs/product/overview.md)：專案總覽（目標、使用者問題、功能清單與現況）
  - [docs/product/feature-design.md](docs/product/feature-design.md)：功能設計（功能怎麼切、依賴方向、上層功能的需求動到底層時改哪一層）
  - [docs/product/features/job-auto-scoring.md](docs/product/features/job-auto-scoring.md)：職缺自動評分（評分規則、提示詞模板、送去評分、依分數排序與篩選、設定的版本與試跑、評分紀錄、驗收標準）
  - [docs/product/features/104-job-scraper.md](docs/product/features/104-job-scraper.md)：104 爬蟲（搜尋條件、抓取中與停止、預覽後存入、驗收標準）
  - [docs/product/features/job-database.md](docs/product/features/job-database.md)：職缺資料庫（職缺表、職缺欄位契約、寫入規則、保存的資訊、驗收標準）
- 技術（怎麼做）：
  - [docs/tech/architecture.md](docs/tech/architecture.md)：系統架構（模組依賴、資料存放、技術選型）
  - [docs/tech/tech-design/job-auto-scoring.md](docs/tech/tech-design/job-auto-scoring.md)：模組分工、提示詞模板、設定頁、`job_scores` 與設定的資料表、舊版評分的改版、LLM 抽象層、驗收對照
  - [docs/tech/tech-design/104-job-scraper.md](docs/tech/tech-design/104-job-scraper.md)：模組分工、抓取作業與預覽的流程、欄位來源、104 API 的限制與請求標頭、驗收對照
  - [docs/tech/tech-design/job-database.md](docs/tech/tech-design/job-database.md)：模組依賴、職缺表的前後端分工、資料表 schema、查詢方式、資料庫改版、驗收對照
  - [docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)：隔離容器與防火牆白名單（所有 AI coding 工具共用）、Remote Control 要的網域與環境變數
  - [docs/tech/ai-coding-setup/claude-code.md](docs/tech/ai-coding-setup/claude-code.md)：Claude Code 專屬的權限規則（deny/ask）
- 慣例：
  - [docs/conventions/documentation.md](docs/conventions/documentation.md)：文件撰寫慣例
  - [docs/conventions/development.md](docs/conventions/development.md)：開發慣例
  - [docs/conventions/templates/](docs/conventions/templates/)：功能文件、技術設計與決策紀錄的範本
- 決策紀錄：[docs/decisions/](docs/decisions/)，依性質分成 product/、tech/、conventions/、ai-coding/

## 使用聲明

本專案僅供個人學習與研究使用：

- 爬蟲程式已限制請求頻率，避免對目標網站造成負擔。
- 抓取到的職缺資料只存在本機（`output/`、`data/` 已排除於版本控制），不會公開或轉散布。
- 職缺與公司資訊的著作權屬於原網站及刊登者。
- 使用前請自行確認並遵守各平台的服務條款。
