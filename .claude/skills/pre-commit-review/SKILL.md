---
name: pre-commit-review
description: commit 前審查暫存區的修改，從 git add、/code-review、逐點判斷修或不修，到 --mark 與 git commit。要 commit 任何修改時都用這個 skill，只改文件的 commit 也一樣。
---

# commit 前審查

為什麼這樣審查，見[決策紀錄：commit 前審查的做法](../../../docs/conventions/decisions/pre-commit-review.md)。

1. 用獨立的指令 `git add` 要 commit 的檔案，不和 `git commit` 寫在同一條指令。
2. 列出不要再報的項目：
   - 已向使用者說明、決定不修的問題。
   - 之後的 commit 才處理的暫時不一致。大改拆成多個 commit 時照拆，不為了消除暫時不一致而合併 commit。
   - 已記在 TODO.md 的已知代價。
3. 執行 `/code-review medium`，args 附上第 2 步的清單，並說明這些項目不要再報。
4. 逐點判斷修或不修：
   - 程式碼：修所有 bug。
   - 文件：只修錯誤或互相矛盾。「可以寫得更細」只在不補就會讓實作做錯時才補，其他不修。
   - 需要使用者決定的修正（要改業務規則、需求或驗收，或有多種合理修法）：先停下來，依 CLAUDE.md 的「向使用者確認問題」詢問，不自行選一種修法。
5. 把這一輪的審查結果寫在一般訊息裡：每一點的內容、修或不修，以及理由。不要只放在詢問的選項前面。
6. 有修正時：
   - 改到程式碼就重跑測試（`uv run pytest`）。
   - 重新 `git add`，把這一輪決定不修的項目加進第 2 步的清單，回到第 3 步。
   - 最多修正三輪：第三輪修正後的審查仍有清單以外的問題時，停下來向使用者說明剩下的問題並詢問怎麼處理，不再自行修改，也不 commit。
7. 沒有要修的問題後，執行 `.claude/hooks/require-review.sh --mark`，再單獨執行 `git commit`，不用 `-a`。
   - 沒有 `--mark`，或 `--mark` 之後暫存區又有變動，commit 會被 PreToolUse hook 擋下；暫存區有變動就回到第 3 步重新審查。
