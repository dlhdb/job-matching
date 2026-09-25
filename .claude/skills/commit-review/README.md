# commit-review：commit 審查流程的說明

這份說明 skill 的目的、組成與設計理由，寫給要修改這個流程的人與 AI agent。執行時的步驟只寫在 [SKILL.md](SKILL.md)，Claude Code 只會載入 SKILL.md，這份不佔用 context。

## 目的

每個 commit 都要經過審查，只改文件的 commit 也一樣。審查是多步驟的流程：commit、執行 `/code-review`、判斷修或不修、修正後重新審查、標記審查通過。這個 skill 要讓流程能收斂：

- 曾經有一次大改的審查跑了 7 輪，原因有三個：
  - 呼叫審查時沒有先說明哪些項目已經決定，同一個已決定的問題被連報 4 次。
  - 大改拆成多個 commit，前一個 commit 留下、要等後面的 commit 才處理的不一致，被當成矛盾回報。
  - 文件沒寫明的細節被反覆挑出來，每次都照著補，補完又挑出新的。
- 另外，每一輪的判斷只寫在詢問的選項前面，使用者看不到審查的結果。

## 組成

- [SKILL.md](SKILL.md)：流程與修正門檻。
- [require-review.sh](../../hooks/require-review.sh)：PreToolUse hook，擋下未審查的 commit 與 push；`--mark` 把 HEAD 記進 `.claude/.reviewed-commits`（不進版控）。記錄檔遺失時，可以用 `--mark <commit>...` 補記已審查過的 commit。
- [settings.json](../../settings.json) 的 `hooks.PreToolUse`：對 Bash 工具掛上 require-review.sh。

## 設計重點與理由

流程寫成 skill：

- 流程的細節只寫在 SKILL.md，CLAUDE.md 與 hook 的提示都只指向它，改流程時只改一處。
- 不寫在 CLAUDE.md：每個 session 都會載入 CLAUDE.md，但多數 session 不 commit；細節越補越長，也和 hook 的提示重複。
- 不記在 Claude 的記憶：記憶不進版控，換一台機器或換一個 AI coding 工具就沒有了，也只在 Claude 想起來時才會用上。

先 commit 再審查：

- `/code-review` 沒指定目標時，審的是還沒 push 的 commit（`@{upstream}...HEAD`）加上工作區的所有修改，沒辦法只審暫存區：
  - 已審過、還沒 push 的 commit 會被再審一次，已決定的問題又被報出來。
  - 大改拆成多個 commit 時，後面 commit 的修改也在工作區，會一起被審到。
- 所以先 commit，再用 git 範圍 `HEAD~1..HEAD` 指定只審最新的 commit。實測只審了該 commit 的檔案，commit message 也能一起審到。
- 原本的做法是先暫存、審查暫存區，通過後才 commit，範圍問題如上，不再採用。
- 修正用 `git commit --amend`，還沒 push 的 commit 可以直接改。
- 每個 commit 審查通過才做下一個：已經疊上後面的 commit 之後，要修前面的 commit 得用 `git rebase -i`，AI coding 工具不支援互動式指令。

hook 同時擋 commit 與 push：

- 擋 commit：HEAD 還沒 push、也還沒 `--mark` 時，擋下下一個 `git commit`，確保每個 commit 做完就審，不會累積到最後。`--amend` 放行，因為那是修正審查問題的方式；amend 後的新 commit 沒有記錄，要重新審查。
- 擋 push：還沒送到遠端的 commit（`git rev-list HEAD --not --remotes`）只要有一個沒記錄就擋下，補上最後一個 commit 沒審就 push 的漏洞。
- `git commit` 與 `git push` 寫在同一條指令時擋下：hook 在整條指令執行前檢查，新的 commit 還不存在，檢查不到。
- 比對指令前，先把 heredoc 的內容與引號內的字串換成佔位字，commit message 裡提到 `git push` 之類的文字才不會被當成指令。
- 指令依 `;`、`&`、`|` 與換行切段，只要有一段是不帶 `--amend` 的 `git commit` 就檢查，`amend` 不能順帶放行後面的新 commit。
- hook 只能確認有沒有審查，判斷修不修仍照 skill。

修正門檻依修改種類分開：

- 程式碼：修所有 bug。
- 文件：只修錯誤或互相矛盾。「可以寫得更細」只在不補就會讓實作做錯時才補。
- 不採用「審查報的問題都修」：對文件來說，「可以寫得更細」永遠挑得出來，都修的話審查不會收斂，7 輪就是這樣來的。

先列出不要再報的清單：

- 呼叫審查時列出已決定不修的問題、之後的 commit 才處理的暫時不一致、已記在 TODO 的已知代價。
- 大改照拆成多個 commit，不為了避免暫時不一致而合併：合併後的 commit 更大，更難審查；暫時不一致只要在呼叫審查時說明，就不會被當成問題。

修正輪數有上限，但判斷一定在詢問之前：

- 每修一輪就重審一次，審查每次都會挑出新的東西，越後面越瑣碎。三輪後仍要修時交給使用者決定，避免自行越修越多。
- 上限只限制自行修正的次數，不省略判斷。原本寫成「第三輪修正後的審查仍有清單以外的問題時，停下來詢問」，「有問題」被讀成「審查有報東西」，結果跳過第 5、6 步，把本來不該修的結果（決策紀錄替代方案裡的理由不夠完整）直接轉給使用者並附上修法。
- 使用者同意的修正修完再審時也一樣先判斷，不因為已經超過上限就把結果原樣轉給使用者。

超出範圍的問題不修：

- 指定 `HEAD~1..HEAD` 之後，工作區有未 commit 的修改時會不會也被審到，還沒驗證。報出來的問題不在這個 commit 裡就略過。

判斷寫在一般訊息裡：

- 每一輪的審查結果與修或不修的理由都寫在一般訊息裡，使用者才看得到，不只放在詢問的選項前面。

## 已知限制

- hook 只檢查 `git commit` 與 `git push`：`rebase`、`merge`、`cherry-pick` 產生的 commit 不擋，但之後的 commit 或 push 仍會檢查到。
- push 時檢查的是 HEAD 的歷史，推送其他分支（`git push origin other-branch`）時不準。
- 指令的解析是簡化的做法，不是完整的 shell 語法：
  - `bash -c` 包起來的指令、變數組出來的指令都認不出來。
  - heredoc 的結束標記只認英數字與底線，帶 `-` 或 `.` 的標記（例如 `EOF-MSG`）內容不會被挖掉；內容提到 `git push` 時會被誤擋，改用 `EOF` 就好。這種情況只會誤擋，不會放行。
- `/code-review` 的主要審查指示不在本機，看不到也改不了。日後要完全掌控審查的範圍與標準，可以改成自訂的審查 subagent。
