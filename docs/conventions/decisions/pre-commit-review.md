# commit 前審查的做法

## 決策背景與問題

每個 commit 前都要先審查修改，只改文件的 commit 也一樣。審查是多步驟的流程：暫存、執行 `/code-review`、判斷修或不修、重新審查，最後標記再 commit。原本這個流程的細節分成三部分，寫在三個地方：

- CLAUDE.md 功能開發流程的第 4 步。
- hook 擋下 commit 時的提示。
- Claude 的記憶。

依 web app 原型改寫 job-database 時，審查跑了 7 輪，原因有三個：

- 呼叫審查時沒有先說明哪些項目已經決定，同一個已決定的問題被連報 4 次。
- 大改拆成多個 commit，前一個 commit 留下、要等後面的 commit 才處理的不一致，被當成矛盾回報。
- 原型沒寫明的細節被反覆挑出來，每次都照著補，補完又挑出新的。

另外，每一輪的判斷只寫在詢問的選項前面，使用者看不到審查的結果。

問題是：審查的流程與修正門檻要寫在哪裡、寫成什麼樣子？

## 考慮過的替代方案

- 維持寫在 CLAUDE.md：
  - 每個 session 都會載入 CLAUDE.md，但多數 session 不 commit。
  - 細節越補越長，也和 hook 擋下 commit 時的提示重複，要改兩處。
- 記在 Claude 的記憶：
  - 記憶不進版控，換一台機器或換一個 AI coding 工具就沒有了。
  - 只在 Claude 想起來時才會用上。
- 審查報的問題都修：
  - 這是原本的做法，不再採用。
  - 對文件來說，「可以寫得更細」永遠挑得出來，都修的話審查不會收斂，7 輪就是這樣來的。
- 為了避免暫時不一致而合併 commit：
  - 合併後的 commit 更大，更難審查。
  - 暫時不一致只要在呼叫審查時說明，就不會被當成問題。

## 最終決策

- 審查流程寫成專案 skill [pre-commit-review](../../../.claude/skills/pre-commit-review/SKILL.md)，細節只寫在 skill。CLAUDE.md 與 hook 的提示都只指向它。
- 修正門檻依修改種類分開：
  - 程式碼：修所有 bug。
  - 文件：只修錯誤或互相矛盾。「可以寫得更細」只在不補就會讓實作做錯時才補。
- 呼叫審查時先列出不要再報的項目：已決定不修的問題、之後的 commit 才處理的暫時不一致、已記在 TODO 的已知代價。
- 大改照拆成多個 commit，不為了避免暫時不一致而合併。
- 每一輪的審查結果與修或不修的理由，都寫在一般訊息裡。
- PreToolUse hook 照舊擋下沒審查過的 commit。hook 只能確認有沒有審查，判斷修不修仍照 skill。
- 影響的文件：
  - [CLAUDE.md](../../../CLAUDE.md#功能開發流程)
  - [pre-commit-review skill](../../../.claude/skills/pre-commit-review/SKILL.md)
  - [require-review.sh](../../../.claude/hooks/require-review.sh)
