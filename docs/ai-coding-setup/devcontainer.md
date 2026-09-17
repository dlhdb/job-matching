# 隔離容器與防火牆

這份文件說明 `.devcontainer/` 提供的隔離執行環境，讓 AI coding agent（目前用 Claude Code，未來可能換用其他工具）可以在這個專案裡自主執行、不必每個操作都手動確認，同時把風險限制在容器內。這是執行環境層級的設定，不屬於任何功能，所以不放在 `docs/features/`。

## 非 root 使用者

容器以 `node` 使用者執行（見 `.devcontainer/Dockerfile`），`node` 對 root 只有一條免密碼 sudo 規則，就是下面的 `init-firewall.sh`，沒有其他 root 權限。這樣即使 agent 在容器內執行了不該執行的指令，影響範圍也侷限在非 root 使用者能碰到的範圍。

## 對外連線防火牆

`.devcontainer/init-firewall.sh` 在 postStartCommand 階段執行，用 `iptables` + `ipset` 把對外連線限制在白名單網域，其餘一律 `REJECT`，改寫自 [Anthropic 官方範例](https://github.com/anthropics/claude-code/tree/main/.devcontainer)。

設計原則是 **fail-closed**：先切成預設拒絕，白名單建置過程中任何一步失敗，網路就維持封鎖，不會因為腳本出錯而變成全開放。

白名單網域分三類：

| 用途 | 網域 |
| :--- | :--- |
| Claude Code 本身 | `api.anthropic.com`、`claude.ai`、`claude.com`、`platform.claude.com`、`mcp-proxy.anthropic.com`、`code.claude.com`、`raw.githubusercontent.com`、`registry.npmjs.org` |
| VS Code 擴充套件 | `marketplace.visualstudio.com`、`vscode.blob.core.windows.net`、`update.code.visualstudio.com` |
| 本專案需要 | `generativelanguage.googleapis.com`（Gemini API）、`www.104.com.tw`（爬蟲目標）、`pypi.org`、`files.pythonhosted.org` |

新增資料來源、外部 API，或換用其他需要連網的 AI coding 工具時，記得把對應網域加進 `init-firewall.sh` 的 `ALLOWED_DOMAINS`，否則容器內的程式碼連不出去。

**注意**：這個防火牆只限制容器自己發出的連線。Claude Code 的 `WebSearch` / `WebFetch` 這類工具是由 Anthropic 伺服器端執行實際查詢，不受此白名單限制；其他 AI coding 工具若有類似「伺服器端代為查詢」的功能，同樣不受影響。
