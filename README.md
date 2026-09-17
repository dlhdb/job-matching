# 求職雷達（job-matching-agent）

自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，過濾出符合自我發展方向的職缺。

## 解決什麼問題

- 避免花大量精力在海量求職平台中人工過濾職缺。
- 了解不同產業、公司現在的發展方向。

## 快速開始

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.14，第一次使用先安裝依賴：

```bash
uv sync
```

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

縣市可以簡寫（如 `台北`），不填則搜尋全台灣。同名的市與縣會對應到清單中先出現的那個，例如 `新竹` 會視為新竹市，要搜新竹縣請寫全名。

### 我想瀏覽或分析抓到的結果

每次執行都會在 `output/104/` 產生同名的兩個檔案：

| 檔案 | 適合用途 |
| :--- | :--- |
| `jobs_104_<關鍵字>_<時間>.csv` | 用 Excel 直接開啟篩選，中文不會亂碼 |
| `jobs_104_<關鍵字>_<時間>.json` | 交給程式或 AI 做後續分析 |

各欄位的意義見 [F2-01 §5.5 欄位字典](docs/features/F2-01-104-job-scraper.md#55-欄位字典)，完整參數說明見 [§5.6](docs/features/F2-01-104-job-scraper.md#56-cli)。

### 我想讓 AI 幫我評估某個職缺適不適合

1. 複製範本，填入自己的偏好與經歷，並在 `.env` 填入 [Gemini API key](https://aistudio.google.com/apikey)：

   ```bash
   cp profile/preferences.example.yaml profile/preferences.yaml
   cp profile/experience.example.md profile/experience.md
   cp .env.example .env
   ```

2. 對爬蟲結果中的一筆職缺評分（省略 `--job-no` 時評分第一筆）：

   ```bash
   uv run src/score_job.py --jobs output/104/<檔名>.json --job-no <職缺代碼>
   ```

結果是包含各維度分數、理由與 0–100 總分的 JSON。薪資太低、公司或職稱在排除清單中的職缺會直接淘汰，不呼叫 AI。想調整提示詞時，加上 `--dry-run` 就只會印出提示詞，不呼叫 AI。評分方式見 [F1-01 工作評分](docs/features/F1-01-job-scoring.md#5-設計)。

## 在隔離環境中讓 Coding Agent 自主執行

[.devcontainer/](.devcontainer/) 提供一個 Docker 容器，讓 AI coding agent（目前設定的是 Claude Code）可以不經逐步確認直接執行：容器內的指令不會碰到主機，對外連線也只允許必要的網域。設計細節見 [docs/ai-coding-setup/devcontainer.md](docs/ai-coding-setup/devcontainer.md)。

1. 安裝 Docker Desktop 與 VS Code 的 [Dev Containers 擴充套件](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)，並啟動 Docker Desktop。
2. 在 VS Code 執行 **Dev Containers: Reopen in Container**。第一次建置會安裝 Python 3.14、依賴與 Claude Code。
3. 在容器的終端機執行：

   ```bash
   claude --dangerously-skip-permissions
   ```

   也可以使用 Claude Code 擴充套件，在模式選單選 **Bypass permissions**。

注意事項：

- 專案資料夾是直接掛載進容器的，agent 的修改會直接出現在主機上。建議在獨立分支上工作。
- 容器內看得到 `.env`，AI API key 建議設定用量上限。
- 允許清單是在容器啟動時把網域解析成 IP。如果某個服務的 IP 變了而連不上，執行 `sudo /usr/local/bin/init-firewall.sh` 重新套用。
- 需要新的網域時，編輯 [init-firewall.sh](.devcontainer/init-firewall.sh) 的 `ALLOWED_DOMAINS`，然後重建容器。

## 專案結構

```
src/
  main.py              uv 產生的樣板，尚未成為真正的進入點
  fetch_104_jobs.py    104 職缺爬蟲
  score_job.py         單筆職缺評分 CLI
  job_scoring/         工作評分邏輯（規則、提示詞、LLM 抽象層）
tests/                 pytest 測試（uv run pytest）
output/104/            爬蟲輸出（不進版控）
profile/               求職偏好與工作經歷（評分用；真實資料不進版控）
.env.example           API key 範本，複製成 .env 後填入
TODO.md                已確認、但尚未要做的事項
.devcontainer/         讓 AI coding 工具自主執行的隔離容器（含對外連線防火牆）
docs/
  README.md            專案總覽：目標、核心技術、功能清單與現況
  features/            各功能的需求、設計與驗收標準（一個功能一份）
  architecture.md      跨功能的資料流
  conventions.md       開發慣例
  ai-coding-setup/     Claude Code 等 AI 輔助開發工具的執行環境設定
```

## 文件導覽

| 文件 | 內容 |
| :--- | :--- |
| [docs/README.md](docs/README.md) | 專案總覽：目標、用例、核心技術、功能清單與現況 |
| [docs/features/F1-01-job-scoring.md](docs/features/F1-01-job-scoring.md) | 單筆職缺評分：需求、評分規則、提示詞、LLM 抽象層、驗收標準 |
| [docs/features/F2-01-104-job-scraper.md](docs/features/F2-01-104-job-scraper.md) | 104 爬蟲：需求、API 限制、欄位字典、驗收標準 |
| [docs/features/F4-01-batch-job-scoring.md](docs/features/F4-01-batch-job-scoring.md) | 職缺批次評分與排序（待實作） |
| [docs/architecture.md](docs/architecture.md) | 系統架構：模組間的資料流與輸入契約 |
| [docs/conventions.md](docs/conventions.md) | 開發慣例 |
| [docs/ai-coding-setup/devcontainer.md](docs/ai-coding-setup/devcontainer.md) | 隔離容器與防火牆白名單（所有 AI coding 工具共用） |
| [docs/ai-coding-setup/claude-code.md](docs/ai-coding-setup/claude-code.md) | Claude Code 專屬的權限規則（deny/ask） |

## 使用聲明

本專案僅供個人學習與研究使用：

- 爬蟲程式已限制請求頻率，避免對目標網站造成負擔。
- 抓取到的職缺資料只存在本機（`output/` 已排除於版本控制），不會公開或轉散布。
- 職缺與公司資訊的著作權屬於原網站及刊登者。使用前請自行確認並遵守各平台的服務條款。
