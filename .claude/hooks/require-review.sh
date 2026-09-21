#!/usr/bin/env bash
# Claude Code PreToolUse hook：暫存區的程式碼修改沒經過 /code-review 就擋下 git commit。
#
# 用法：
#   require-review.sh          由 hook 呼叫，從 stdin 讀 Bash 工具的輸入
#   require-review.sh --mark   審查完成後執行，記下目前暫存區的 hash
#
# 暫存區只有 Markdown 檔時直接放行。
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
marker=".claude/.reviewed-diff"

staged_hash() {
    git diff --cached --binary | sha256sum | cut -d' ' -f1
}

if [[ "${1:-}" == "--mark" ]]; then
    staged_hash > "$marker"
    echo "已記錄審查過的暫存區：$(cat "$marker")"
    exit 0
fi

command=$(jq -r '.tool_input.command // ""')
# git 與子指令之間可能夾著全域選項（-C <路徑>、-c <設定>、--no-pager 等）
git_sub='(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+'
grep -qE "${git_sub}commit" <<< "$command" || exit 0

# hook 在整條指令執行前跑，同一條指令裡的 git add 或 commit -a 還沒生效，算出的 hash 會不準
if grep -qE "${git_sub}add|${git_sub}commit[^;&|]*[[:space:]](-a|--all|-[a-zA-Z]*a[a-zA-Z]*)([[:space:]]|\$)" <<< "$command"; then
    echo "請先用獨立的指令 git add，再單獨執行 git commit（不要用 -a），hook 才能比對審查過的暫存區。" >&2
    exit 2
fi

# 先存成變數再 grep：直接接管線時 grep -q 提早結束，git 會因 SIGPIPE 失敗，pipefail 下整個判斷變成假
staged_files=$(git diff --cached --name-only) || { echo "無法讀取暫存區檔案清單，請確認 git 狀態後再 commit。" >&2; exit 2; }
if grep -qvE '\.md$' <<< "$staged_files"; then
    if [[ -f "$marker" && "$(cat "$marker")" == "$(staged_hash)" ]]; then
        exit 0
    fi
    echo "暫存區的修改尚未審查。請先執行 /code-review 並處理發現的問題，修正後重新審查，直到除了已向使用者說明、決定不修的問題以外沒有其他問題為止（最多修正三輪，超過就停下來詢問使用者），確認暫存區是最終內容後執行 .claude/hooks/require-review.sh --mark，再重新 commit。" >&2
    exit 2
fi
exit 0
