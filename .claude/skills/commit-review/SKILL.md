---
name: commit-review
description: commit 後、下一個 commit 或 push 前審查最新的 commit，從列出 commit 怎麼拆、檢查文件格式、git commit、/code-review HEAD~1..HEAD、逐點判斷修或不修、amend，到 --mark。要 commit 任何修改時都用這個 skill，只改文件的 commit 也一樣。
---

# commit 審查

為什麼這樣審查，見同目錄的 [README.md](README.md)。

1. 列出 commit 怎麼拆：每個 commit 包含哪些檔案、依什麼順序 commit，盡量以檔案為單位拆。一次只處理一個 commit，審查通過才做下一個。
2. 先檢查文件格式，再 commit：
   - 這個 commit 有 `.md` 檔時，把檔案清單交給 `doc-format-review` subagent，它會檢查改到的段落並直接修正。
   - 看過它的修改，確認沒有改到意思。
   - 把修正與沒修的項目寫在一般訊息裡。
   - `git add` 這個 commit 的檔案，然後 `git commit`。
3. 列出不要再報的項目，每項寫位置、內容與理由：
   - 已向使用者說明、決定不修的問題。
   - 之後的 commit 才處理的暫時不一致，註明哪一個 commit 會處理；到了那個 commit 就從清單拿掉。大改照拆成多個 commit，不為了消除暫時不一致而合併 commit。
   - 已記在 `backlog/TODO.md` 的已知代價。
4. 執行 `/code-review medium HEAD~1..HEAD <說明>`：
   - 說明寫這是 N 個 commit 中的第幾個，加上第 3 步的清單，並說明這些項目不要再報。
   - 它在背景執行，等審查結果回來再往下。
5. 逐點判斷修或不修：
   - 不在這個 commit 裡的問題（例如工作區還沒 commit 的修改）：不修，註明「超出範圍」。
   - 程式碼：修所有 bug。
   - 文件：只修錯誤或互相矛盾。「可以寫得更細」只在不補就會讓實作做錯時才補，其他不修。
   - 需要使用者決定的修正（要改業務規則、需求或驗收，或有多種合理修法）：先停下來詢問使用者，不自行選一種修法。
6. 把這一輪的判斷寫在一般訊息裡：每一點的內容、修或不修，以及理由。這是審查後的判斷，不是重列 `/code-review` 的結果，也不要只放在詢問的選項前面。
7. 有修正時：
   - 改到程式碼就重跑測試（`uv run pytest`）。
   - 改到 `.md` 檔時，amend 前同樣先照第 2 步檢查文件格式。
   - `git add` 後 `git commit --amend`，把這一輪決定不修的項目加進第 3 步的清單，回到第 4 步。
   - 最多自行修正三輪：第三輪修正後的審查結果仍照第 5、6 步判斷。全部判斷為不修時，寫出理由後照第 8 步 `--mark`；只要有一點判斷為要修，就寫出不修各點的理由，再向使用者說明要修的問題並詢問怎麼處理，不再自行修改，也不 `--mark`。
   - 使用者同意的修正修完後，重新審查的結果同樣先照第 5、6 步判斷，要修的仍先詢問。
8. 沒有要修的問題後，執行 `.claude/hooks/require-review.sh --mark`，再回到第 2 步處理下一個 commit。
   - 沒有 `--mark` 的 commit，之後的 `git commit`（`--amend` 除外）與 `git push` 會被 PreToolUse hook 擋下。
   - `--mark` 之後又 amend，要回到第 4 步重新審查。
   - `git commit` 與 `git push` 要分成兩條指令。
