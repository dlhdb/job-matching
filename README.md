# 求職雷達（job-matching-agent）

自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，過濾出符合自我發展方向的職缺。

## 解決什麼問題

- 避免花大量精力在海量求職平台中人工過濾職缺。
- 了解不同產業、公司現在的發展方向。

## 快速開始

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.14，第一次使用先執行設定腳本：

```bash
scripts/setup-dev-env.sh
```

腳本會做兩件事，可以重複執行：

- 安裝依賴（`uv sync`）。
- 設定 git filter，`git add` 時自動移除 notebook 的輸出，避免職缺資料進版控。

每次重新 clone 都要再執行一次：

- filter 設定存在 `.git/config`，不會跟著 clone 下來。
- 沒設定時 `git add` 不會有任何警告，notebook 的輸出會直接進版控。

使用 devcontainer 時，建立容器會自動執行這支腳本。

### 我想先隨便看看有哪些職缺

用互動模式，照提示依序輸入關鍵字、縣市、頁數與職缺性質：

```bash
uv run src/fetch_104_jobs.py
```

### 我已經知道要找什麼

用命令列模式直接指定條件，例如在台北市找全職的 Python 職缺，抓 2 頁：

```bash
uv run src/fetch_104_jobs.py -k Python -a 台北市 -t 1 -p 2
```

### 我想一次搜尋多個相關職稱

用逗號分隔多個關鍵字，重複的職缺會自動合併：

```bash
uv run src/fetch_104_jobs.py -k "後端工程師,Backend,Python" -a 新竹
```

縣市的寫法：

- 可以簡寫，例如 `台北`。
- 不填則搜尋全台灣。
- 同名的市與縣會對應到清單中先出現的那個。例如 `新竹` 會視為新竹市，要搜新竹縣請寫全名。

### 我想瀏覽或分析抓到的結果

每次執行都會在 `output/104/` 產生同名的兩個檔案：

- `jobs_104_<關鍵字>_<時間>.csv`：用 Excel 直接開啟篩選，中文不會亂碼
- `jobs_104_<關鍵字>_<時間>.json`：交給程式或 AI 做後續分析

- 各欄位的意義見 [job-database §7.2.1 職缺欄位契約](docs/product/features/job-database.md#721-職缺欄位契約)。
- 完整參數說明見 [§10.2.1](docs/product/features/104-job-scraper.md#1021-cli)。
- 想做統計或篩選時，打開 [notebooks/analyze_104_jobs.ipynb](notebooks/analyze_104_jobs.ipynb)，kernel 選專案的虛擬環境（devcontainer 內是 `~/.venv/bin/python`）。

### 我想累積每次抓到的職缺，看出哪些是新的

每次抓取完，職缺也會寫進 `data/jobs.db`（SQLite）：

- 同一筆職缺只保留一列，並記錄第一次與最後一次被抓到的時間。
- 加上 `--no-db` 可以只輸出檔案。

以前抓的 JSON 可以補匯入，重複匯入同一個檔案不會改變資料庫：

```bash
uv run src/import_jobs.py output/104/*.json
```

用 `pandas.read_sql` 或任何 SQLite 工具讀取即可，保存的資訊見 [job-database §7.2.2](docs/product/features/job-database.md#722-保存的資訊)，資料表 schema 見 [job-database 技術設計](docs/tech/tech-design/job-database.md#32-資料表)。

### 我想讓 AI 幫我評估職缺適不適合

1. 複製範本，填入自己的偏好與經歷，並在 `.env` 填入 [Gemini API key](https://aistudio.google.com/apikey)：

   ```bash
   cp profile/preferences.example.yaml profile/preferences.yaml
   cp profile/experience.example.md profile/experience.md
   cp .env.example .env
   ```

2. 先讓職缺進到 `data/jobs.db`（爬蟲預設會寫入，以前的 JSON 用上一節的 `import_jobs.py` 匯入），再評所有還沒評分的職缺：

   ```bash
   uv run src/score_job.py
   ```

   - 最近出現的職缺先評，已經有評分（自動或手動）的職缺不會再評。
   - 結果寫進同一個資料庫，終端機只顯示進度與摘要；個別職缺評分失敗時會跳過並列在摘要中，下次執行會再評。

3. 只想評某幾筆，或換了偏好、經歷之後要重評時，加上 `--job-no`，已經評過的也會重評：

   ```bash
   uv run src/score_job.py --job-no <職缺代碼> [<職缺代碼> ...]
   ```

- 結果包含各維度分數、理由與 0–100 總分，每次評分都新增一筆紀錄，以最新的一筆為準。
- 評分結果以 `pandas.read_sql` 或任何 SQLite 工具讀取 `job_scores` 表，各維度的分數與理由在 `評分明細` 欄（JSON）。
- 薪資太低、公司或職稱在排除清單中的職缺會直接淘汰，不呼叫 AI。
- 想換一份偏好、經歷或模型比較結果時，加上 `--dry-run` 試跑（必須搭配 `--job-no`）：照常呼叫 AI 評分，結果寫到 `output/scores/dryrun_<開始時間>.json` 與 `.csv`，不寫入資料庫。
- 評分方式見 [job-auto-scoring 自動評分並看懂每個分數](docs/product/features/job-auto-scoring.md#4-自動評分並看懂每個分數score)。

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
src/            程式碼：爬蟲、職缺資料庫、評分 CLI 與評分邏輯
tests/          測試
notebooks/      分析資料的 Jupyter notebook
scripts/        工具腳本
profile/        使用者的求職偏好與工作經歷（真實資料不進版控）
output/         應用程式輸出結果（不進版控）
data/           職缺資料庫 jobs.db（不進版控）
docs/           文件：product/（產品）、tech/（技術）、conventions/（慣例）
.devcontainer/  開發環境隔離容器設定
```

## 文件導覽

文件依讀者分成產品、技術與慣例三區，完整索引與撰寫流程見 [docs/README.md](docs/README.md)。

- 產品（為什麼做、做什麼）：
  - [docs/product/overview.md](docs/product/overview.md)：專案總覽（目標、使用者問題、功能清單與現況）
  - [docs/product/features/job-auto-scoring.md](docs/product/features/job-auto-scoring.md)：職缺自動評分（需求、評分規則、提示詞、整批評分與結果檔、驗收標準）
  - [docs/product/features/job-score-database.md](docs/product/features/job-score-database.md)：評分資料庫（評分紀錄契約、保存規則、依分數查詢、驗收標準）
  - [docs/product/features/104-job-scraper.md](docs/product/features/104-job-scraper.md)：104 爬蟲（需求、CLI、輸出檔、寫入資料庫與匯入、驗收標準）
  - [docs/product/features/job-database.md](docs/product/features/job-database.md)：職缺資料庫（需求、職缺欄位契約、寫入規則、保存的資訊、驗收標準）
  - [docs/product/decisions/](docs/product/decisions/)：產品取捨的決策紀錄
- 技術（怎麼做）：
  - [docs/tech/architecture.md](docs/tech/architecture.md)：系統架構（模組依賴、資料存放、技術選型）
  - [docs/tech/tech-design/job-auto-scoring.md](docs/tech/tech-design/job-auto-scoring.md)：模組分工、`job_scores` 的自動評分欄位、LLM 抽象層、驗收對照
  - [docs/tech/tech-design/job-score-database.md](docs/tech/tech-design/job-score-database.md)：`job_scores` 資料表、評分查詢、驗收對照
  - [docs/tech/tech-design/104-job-scraper.md](docs/tech/tech-design/104-job-scraper.md)：104 API 的限制與請求標頭、欄位來源、寫入資料庫與匯入、驗收對照
  - [docs/tech/tech-design/job-database.md](docs/tech/tech-design/job-database.md)：模組依賴、資料表 schema、查詢方式、驗收對照
  - [docs/tech/decisions/](docs/tech/decisions/)：技術取捨的決策紀錄
  - [docs/tech/ai-coding-setup/devcontainer.md](docs/tech/ai-coding-setup/devcontainer.md)：隔離容器與防火牆白名單（所有 AI coding 工具共用）、Remote Control 要的網域與環境變數
  - [docs/tech/ai-coding-setup/claude-code.md](docs/tech/ai-coding-setup/claude-code.md)：Claude Code 專屬的權限規則（deny/ask）
- 慣例：
  - [docs/conventions/documentation.md](docs/conventions/documentation.md)：文件撰寫慣例
  - [docs/conventions/development.md](docs/conventions/development.md)：開發慣例
  - [docs/conventions/decisions/](docs/conventions/decisions/)：文件與開發流程的決策紀錄

## 使用聲明

本專案僅供個人學習與研究使用：

- 爬蟲程式已限制請求頻率，避免對目標網站造成負擔。
- 抓取到的職缺資料只存在本機（`output/`、`data/` 已排除於版本控制），不會公開或轉散布。
- 職缺與公司資訊的著作權屬於原網站及刊登者。
- 使用前請自行確認並遵守各平台的服務條款。
