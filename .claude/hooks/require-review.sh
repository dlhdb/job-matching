#!/usr/bin/env bash
# Claude Code PreToolUse hook：上一個 commit 還沒審查就擋下下一個 git commit，有 commit 還沒審查就擋下 git push。
# 設計理由見 .claude/skills/commit-review/README.md。
#
# 用法：
#   require-review.sh          由 hook 呼叫，從 stdin 讀 Bash 工具的輸入
#   require-review.sh --mark [<commit>...]
#                              審查完成後執行，把指定的 commit（預設 HEAD）記為已審查；
#                              記錄檔遺失時，可以指定已審查過的 commit 補記
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
marker=".claude/.reviewed-commits"

if [[ "${1:-}" == "--mark" ]]; then
    shift
    for rev in "${@:-HEAD}"; do
        git rev-parse --verify "$rev^{commit}" >> "$marker"
        echo "已記錄審查過的 commit：$(git rev-parse --short "$rev")"
    done
    exit 0
fi

# 還沒送到遠端、也不在記錄檔裡的 commit
unreviewed() {
    git rev-list HEAD --not --remotes 2>/dev/null | grep -vxF -f <(cat "$marker" 2>/dev/null; echo) || true
}

# heredoc 的內容與引號內的字串換成佔位字，commit message 裡提到 git push 之類的文字才不會被當成指令
# heredoc 只去掉內容行，保留 <<EOF 同一行後面的指令；引號由左到右一次處理，單雙引號才不會交錯配對
command=$(jq -r '.tool_input.command // ""' | perl -0pe '
    s/<<-?[ \t]*([\x27"]?)(\w+)\1([^\n]*)\n(?:.*?\n)?[ \t]*\2[ \t]*(?=\n|\z)/Q$3/gs;
    s/\x27[^\x27]*\x27|"(?:[^"\\]|\\.)*"/Q/gs;
')
# git 與子指令之間可能夾著全域選項（-C <路徑>、-c <設定>、--no-pager 等）
git_sub='(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+'
# 依 ; & | 與換行切段，一段一個指令
segments=$(tr ';&|' '\n\n\n' <<< "$command")
commits=$(grep -E "${git_sub}commit" <<< "$segments" || true)
has_commit=false
has_push=false
[[ -n "$commits" ]] && has_commit=true
grep -qE "${git_sub}push" <<< "$segments" && has_push=true

# hook 在整條指令執行前跑，同一條指令裡新產生的 commit 還不存在，push 前檢查不到
if $has_commit && $has_push; then
    echo "請把 git commit 與 git push 分成兩條指令執行，hook 才能檢查要 push 的 commit 是否都審查過。" >&2
    exit 2
fi

if $has_commit; then
    # amend 是修正審查問題的方式，amend 後的新 commit 會在下一個 commit 或 push 前被檢查；
    # 只要有一段是不帶 --amend 的 commit 就要檢查
    head=$(git rev-parse -q --verify HEAD || true)
    if [[ -n "$head" ]] && grep -qvE "[[:space:]]--amend([[:space:]]|$)" <<< "$commits" \
        && unreviewed | grep -qxF "$head"; then
        echo "上一個 commit $(git rev-parse --short HEAD) 尚未審查。請照 commit-review skill 審查它，執行 .claude/hooks/require-review.sh --mark 後再 commit。" >&2
        exit 2
    fi
fi

if $has_push; then
    pending=$(unreviewed)
    if [[ -n "$pending" ]]; then
        echo "下列 commit 尚未審查，請照 commit-review skill 審查並 --mark 後再 push：" >&2
        git log --no-walk --format='  %h %s' $pending >&2
        exit 2
    fi
fi

exit 0
