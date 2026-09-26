# 隔離容器與防火牆

這份文件說明 `.devcontainer/` 提供的隔離執行環境：

- 讓 AI coding agent（目前用 Claude Code，未來可能換用其他工具）可以在這個專案裡自主執行，不必每個操作都手動確認。
- 同時把風險限制在容器內。

這是執行環境層級的設定，不屬於任何功能，所以不放在 `docs/product/features/`，而是放在技術文件區。

## 非 root 使用者

- 容器以 `node` 使用者執行（見 `.devcontainer/Dockerfile`）。
- `node` 對 root 只有一條免密碼 sudo 規則，就是下面的 `init-firewall.sh`，沒有其他 root 權限。
- 即使 agent 在容器內執行了不該執行的指令，影響範圍也侷限在非 root 使用者能碰到的範圍。

## 容器內的工具

- 系統工具都在 `.devcontainer/Dockerfile` 建置時以 apt 安裝，此時防火牆尚未啟用。
- 容器啟動後無法補裝：`node` 沒有 root 權限，防火牆也沒有放行 apt 的套件來源。
- 需要新工具時加進 Dockerfile，再重建容器（「Dev Containers: Rebuild Container」）。
- `sqlite3`：在終端機查詢 SQLite 資料庫，例如 `sqlite3 data/jobs.db`。
  - VS Code 的 SQLite 擴充套件（例如 vscode-sqlite）也要呼叫系統的 `sqlite3`。
  - 這些擴充套件內建的備用執行檔只支援 x86，在 ARM（例如 Apple Silicon）的容器中無法使用。
- `chromium`：Playwright 在容器內以真的瀏覽器跑測試。
  - 用 apt 的 Chromium，不用 `playwright install` 下載：防火牆沒有放行 Playwright 的下載來源。
  - `playwright install --with-deps` 還要 root 才能裝瀏覽器需要的系統函式庫，apt 安裝 `chromium` 時會一起裝好。
  - Playwright 預設只找自己下載的瀏覽器，啟動時要用 `executable_path` 指定 `/usr/bin/chromium`。
- `fonts-noto-cjk`：中文字型。
  - 沒有中文字型時：
    - 瀏覽器會把中文顯示成方塊，截圖沒辦法看。
    - 文字的寬高不對。

## 虛擬環境、前端依賴與 git 設定

專案資料夾以 bind mount 掛進容器，主機與容器看到的是同一份 `/workspace`，包含 `.venv/` 與 `.git/config`：

- 虛擬環境分開放：`UV_PROJECT_ENVIRONMENT` 把容器的虛擬環境指到 `/home/node/.venv`。
  - 原因：`/workspace/.venv` 是主機（macOS）建立的，Python 連結指向主機路徑，在容器內無法執行。
  - VS Code 會把 `/workspace/.venv` 標成推薦的 interpreter，但容器內要選 `/home/node/.venv/bin/python`。notebook 的 kernel 也一樣。
- 前端依賴分開放：`devcontainer.json` 把一個 Docker volume 掛到 `/workspace/frontend/node_modules`，容器內的 `npm` 裝進 volume，不寫進主機的資料夾。
  - 原因和虛擬環境相同：esbuild、rollup 這類套件會裝依作業系統編譯的執行檔，主機（macOS）與容器（Linux）共用同一份 `node_modules` 時會互相覆蓋，另一邊就無法執行。
  - 不用環境變數改路徑：npm 沒有像 `UV_PROJECT_ENVIRONMENT` 的設定，只能從掛載點分開。
  - 擁有者：空的 volume 第一次掛上時，沿用映像檔裡同一路徑的擁有者，所以 Dockerfile 先建好這個目錄並交給 `node`，`npm` 才寫得進去。
- git filter 不寫絕對路徑：
  - `postCreateCommand` 執行 `scripts/setup-dev-env.sh`，安裝依賴並設定 nbstripout filter，在 `git add` 時移除 notebook 的輸出。
  - 問題：`nbstripout --install` 會把 Python 的絕對路徑寫進 `.git/config`。主機與容器共用這份設定，兩邊的虛擬環境路徑卻不同。
  - 做法：改由腳本寫入 `uv run --no-sync python -m nbstripout`，讓兩邊各自的 uv 找到自己的虛擬環境。
- filter 失敗時擋下：filter 設定了 `required`，環境裡沒有 nbstripout 時 `git add` 會報錯，不會把輸出存進去。

## 對外連線防火牆

`.devcontainer/init-firewall.sh`，改寫自 [Anthropic 官方範例](https://github.com/anthropics/claude-code/tree/main/.devcontainer)：

- 在 postStartCommand 階段執行。
- 用 `iptables` + `ipset` 把對外連線限制在白名單網域，其餘一律 `REJECT`。
- 設計原則是 fail-closed：先切成預設拒絕，白名單建置過程中任何一步失敗，網路就維持封鎖，不會因為腳本出錯而變成全開放。

白名單網域分四類：

- Claude Code 本身：`api.anthropic.com`、`claude.ai`、`claude.com`、`platform.claude.com`、`mcp-proxy.anthropic.com`、`code.claude.com`、`raw.githubusercontent.com`、`registry.npmjs.org`
  - 自動更新走 `registry.npmjs.org`：容器內是 npm 全域安裝（Dockerfile 的 `npm install -g @anthropic-ai/claude-code`），更新從 npm 取得新版，不下載原生執行檔。`claude doctor` 的 `Config install method` 顯示 `global`、`Last update attempt` 顯示結果。
  - 不放行 `downloads.claude.ai`：這是 Claude Code 的 CDN，只有原生安裝版的自動更新一定要走它，npm 安裝版用不到。模型目錄與官方 plugin 市集的資料 CDN 上也有，但不是唯一來源——該網域被擋的狀態下，`~/.claude/cache/model-catalog/` 仍會更新，plugin 市集則在 GitHub（`anthropics/claude-plugins-official`）。改用原生安裝版時才需要加進白名單。
- Claude Code 的 Remote Control（見下方「Remote Control 與遙測」）：
  - `bridge.claudeusercontent.com`：連線用的 websocket，手機或網頁的操作從這裡進來、session 的輸出從這裡回去。它目前解析到的 IP 與 `api.anthropic.com` 相同，但這只是巧合，仍要獨立列出。
  - `cdn.growthbook.io`：feature flag 的來源，Claude Code 用它判斷 Remote Control 是否可用。Claude Code 相關的網域中只有這個不是 Anthropic 的機器（GrowthBook 的 CDN，掛在 Fastly）。
- VS Code 擴充套件：`marketplace.visualstudio.com`、`vscode.blob.core.windows.net`、`update.code.visualstudio.com`
- 本專案需要：`generativelanguage.googleapis.com`（Gemini API）、`www.104.com.tw`（爬蟲目標）、`pypi.org`、`files.pythonhosted.org`

新增資料來源、外部 API，或換用其他需要連網的 AI coding 工具時，要把對應網域加進 `init-firewall.sh` 的 `ALLOWED_DOMAINS`，否則容器內的程式碼連不出去。清單是逐一解析網域取 IP 加進 ipset，子網域不會被母網域涵蓋，例如 `claude.ai` 不會一併放行 `downloads.claude.ai`，兩者解析到的 IP 不同。

`ALLOWED_DOMAINS` 改了要重建容器才會生效：腳本在 build 時 COPY 到 `/usr/local/bin/init-firewall.sh`，postStartCommand 執行的是那份副本，不是 `.devcontainer/` 底下的原始檔。

這個防火牆**只**限制容器自己發出的連線：

- Claude Code 的 `WebSearch` / `WebFetch` 這類工具，由 Anthropic 伺服器端執行實際查詢，不受此白名單限制。
- 其他 AI coding 工具若有類似「伺服器端代為查詢」的功能，同樣不受影響。

## Remote Control 與遙測

Remote Control 讓手機或 claude.ai/code 操作容器內的 Claude Code session。要能用，除了上面兩個網域，`devcontainer.json` 的 `containerEnv` **不能**設 `DISABLE_TELEMETRY`：

- Claude Code 以 feature flag 判斷這個帳號能不能用 Remote Control，而 `DISABLE_TELEMETRY` 會把整個 feature flag 評估一起關掉，Remote Control 就固定初始化失敗。
- 兩個條件缺一不可，且錯誤訊息不同，可用 `claude doctor` 的「Remote Control」段落分辨：
  - 設了 `DISABLE_TELEMETRY`：`Feature-flag evaluation disabled (disabled by DISABLE_TELEMETRY)`
  - 少了 `cdn.growthbook.io`：`the feature-flag service was unreachable (offline or blocked)`
  - 兩者都滿足：不列出診斷項目，只顯示 `Control this session from claude.ai/code or the Claude mobile app`
- 代價是 Claude Code 會送使用遙測到 `api.anthropic.com`。只關錯誤回報用 `DISABLE_ERROR_REPORTING`，它不影響 feature flag。

這條通道會把 session 的完整對話往外送、並接受外部指令，這正是 Remote Control 的定義。不需要從容器外操作 session 時，移除上述兩個網域並設回 `DISABLE_TELEMETRY` 即可關閉。
