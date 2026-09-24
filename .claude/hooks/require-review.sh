#!/usr/bin/env bash
# Claude Code PreToolUse hook：暫存區的修改沒經過 /code-review 就擋下 git commit。
#
# 用法：
#   require-review.sh          由 hook 呼叫，從 stdin 讀 Bash 工具的輸入
#   require-review.sh --mark   審查完成後執行，記下目前暫存區的 hash
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

if [[ -f "$marker" && "$(cat "$marker")" == "$(staged_hash)" ]]; then
    exit 0
fi
echo "暫存區的修改尚未審查。請照 pre-commit-review skill 審查，確認暫存區是最終內容後執行 .claude/hooks/require-review.sh --mark，再重新 commit。" >&2
exit 2
