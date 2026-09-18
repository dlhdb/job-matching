# 隔離容器與防火牆

這份文件說明 `.devcontainer/` 提供的隔離執行環境，讓 AI coding agent（目前用 Claude Code，未來可能換用其他工具）可以在這個專案裡自主執行、不必每個操作都手動確認，同時把風險限制在容器內。這是執行環境層級的設定，不屬於任何功能，所以不放在 `docs/features/`。

## 非 root 使用者

容器以 `node` 使用者執行（見 `.devcontainer/Dockerfile`），`node` 對 root 只有一條免密碼 sudo 規則，就是下面的 `init-firewall.sh`，沒有其他 root 權限。這樣即使 agent 在容器內執行了不該執行的指令，影響範圍也侷限在非 root 使用者能碰到的範圍。

## 虛擬環境與 git 設定

專案資料夾以 bind mount 掛進容器，主機與容器看到的是同一份 `/workspace`，包含 `.venv/` 與 `.git/config`：

- 虛擬環境分開放：`UV_PROJECT_ENVIRONMENT` 把容器的虛擬環境指到 `/home/node/.venv`。`/workspace/.venv` 是主機（macOS）建立的，Python 連結指向主機路徑，在容器內無法執行。VS Code 會把它標成推薦的 interpreter，但容器內要選 `/home/node/.venv/bin/python`，notebook 的 kernel 也一樣。
- git filter 不寫絕對路徑：`postCreateCommand` 執行 `scripts/setup-dev-env.sh`，安裝依賴並設定 nbstripout filter，在 `git add` 時移除 notebook 的輸出。`nbstripout --install` 會把 Python 的絕對路徑寫進 `.git/config`，但主機與容器共用這份設定，兩邊的虛擬環境路徑不同，所以改由腳本寫入 `uv run --no-sync python -m nbstripout`，讓兩邊各自的 uv 找到自己的虛擬環境。
- filter 失敗時擋下：filter 設定了 `required`，環境裡沒有 nbstripout 時 `git add` 會報錯，不會把輸出存進去。

## 對外連線防火牆

`.devcontainer/init-firewall.sh` 在 postStartCommand 階段執行，用 `iptables` + `ipset` 把對外連線限制在白名單網域，其餘一律 `REJECT`，改寫自 [Anthropic 官方範例](https://github.com/anthropics/claude-code/tree/main/.devcontainer)。

設計原則是 fail-closed：先切成預設拒絕，白名單建置過程中任何一步失敗，網路就維持封鎖，不會因為腳本出錯而變成全開放。

白名單網域分三類：

- Claude Code 本身：`api.anthropic.com`、`claude.ai`、`claude.com`、`platform.claude.com`、`mcp-proxy.anthropic.com`、`code.claude.com`、`raw.githubusercontent.com`、`registry.npmjs.org`
- VS Code 擴充套件：`marketplace.visualstudio.com`、`vscode.blob.core.windows.net`、`update.code.visualstudio.com`
- 本專案需要：`generativelanguage.googleapis.com`（Gemini API）、`www.104.com.tw`（爬蟲目標）、`pypi.org`、`files.pythonhosted.org`

新增資料來源、外部 API，或換用其他需要連網的 AI coding 工具時，記得把對應網域加進 `init-firewall.sh` 的 `ALLOWED_DOMAINS`，否則容器內的程式碼連不出去。

**注意**：這個防火牆只限制容器自己發出的連線。Claude Code 的 `WebSearch` / `WebFetch` 這類工具是由 Anthropic 伺服器端執行實際查詢，不受此白名單限制；其他 AI coding 工具若有類似「伺服器端代為查詢」的功能，同樣不受影響。
