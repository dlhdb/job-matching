#!/bin/sh
# 建立開發環境：安裝依賴，並設定 git filter。
# 主機與 devcontainer 都執行這支腳本（devcontainer 由 postCreateCommand 自動執行），可重複執行。
set -eu

cd "$(git rev-parse --show-toplevel)"

if ! command -v uv >/dev/null 2>&1; then
    echo "[-] 找不到 uv，請先安裝：https://docs.astral.sh/uv/" >&2
    exit 1
fi

echo "⏳ 安裝依賴（uv sync）"
uv sync

# nbstripout git filter：git add 時移除 notebook 輸出，工作目錄中的 notebook 保留輸出。
# 哪些檔案套用 filter 由 .gitattributes 決定，這裡只設定 filter 要執行的指令（寫進 .git/config）。
#
# 不用 `nbstripout --install`：它會寫入 Python 的絕對路徑，而容器與主機共用同一份 .git/config，
# 兩邊的虛擬環境路徑不同。改用 uv run，由各自的 uv 找到對應的虛擬環境。
# --no-sync 讓 git add 時不會順便改動虛擬環境；環境裡沒有 nbstripout 時 filter 會失敗，
# 搭配 required=true，git add 會報錯而不是把輸出直接存進去。
echo "⏳ 設定 nbstripout git filter"
git config filter.nbstripout.clean "uv run --no-sync python -m nbstripout"
git config filter.nbstripout.smudge cat
git config filter.nbstripout.required true
git config diff.ipynb.textconv "uv run --no-sync python -m nbstripout -t"

echo "🎉 開發環境設定完成"
