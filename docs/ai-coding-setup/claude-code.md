# Claude Code 權限規則

這份文件說明 Claude Code 專屬的權限設定與理由。容器層級的隔離與防火牆是所有 AI coding 工具共用的設定，見 [devcontainer.md](devcontainer.md)。

## 權限規則（`.claude/settings.json`）

跨越任何權限模式（包含未來若切換到 bypass 模式）都要守住的規則，寫在專案共用的 `.claude/settings.json`（會進版控，套用到所有人）。比對順序是 `deny` → `ask` → `allow`，`deny` 優先。

`deny`，完全擋下，沒有合理使用情境：

- `Read(*.env)`：讀取環境變數檔（可能含 API key）
- `Bash(rm -rf *)`：遞迴強制刪除
- `Bash(git push --force*)` / `-f*` / `* --force*` / `* -f`：強制推送，會覆蓋遠端歷史
- `Bash(git reset --hard*)`：捨棄工作目錄與 commit 的變更
- `Bash(git clean -f*)`：強制刪除未追蹤的檔案
- `Bash(git branch -D*)`：強制刪除分支

`ask`，一定跳出來問，即使之後切到 bypass 模式也一樣：

- `Bash(git push*)`：會影響遠端這個共享狀態
- `Bash(gh pr create*)` / `merge*` / `close*`：PR 操作對其他協作者可見
- `Bash(git checkout -- *)` / `Bash(git restore *)`：會捨棄尚未提交的修改

新增規則時，判斷標準是：`deny` 給「這個專案裡沒有合理使用情境、且難以復原」的操作；`ask` 給「會影響共享狀態（遠端、PR），但有合理使用情境」的操作。單純危險但本地、可復原的操作（例如一般的 `git commit --amend`）不需要特別設規則，交給日常的權限提示處理即可。
