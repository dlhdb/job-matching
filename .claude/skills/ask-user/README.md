# ask-user：向使用者提問的說明

這份說明 skill 的目的、組成與設計理由，寫給要修改提問方式的人與 AI agent。執行時的規則只寫在 [SKILL.md](SKILL.md)，Claude Code 只會載入 SKILL.md，這份不佔用 context。

## 目的

需要使用者做決定時，讓使用者最容易理解、也最容易回答：

- 問題難懂時，使用者得自己回想脈絡，決定變慢，也容易答錯。
- 問題難答時，使用者得自己組織答案，例如開放式的「你想怎麼處理？」。

## 組成

- [SKILL.md](SKILL.md)：提問原則與詢問方式。
- [CLAUDE.md 的「向使用者確認問題」](../../../CLAUDE.md#向使用者確認問題)：只有一句，指向這個 skill。
- `to-be-confirm/`：問卷放這裡，列在 `.gitignore`，不進版控。

## 設計重點與理由

寫成 skill：

- 規則只寫在 SKILL.md，CLAUDE.md 只指向它，改提問方式時只改一處。
- 不寫在 CLAUDE.md：每個 session 都會載入 CLAUDE.md，但只有要提問時才用得到這些規則。
- 不記在 Claude 的記憶：記憶不進版控，換一台機器或換一個 AI coding 工具就沒有了。

確保提問前有載入 skill：

- 模型傾向少用 skill，所以 description 寫得積極：就算只是一題是非題，提問前也要先用。
- CLAUDE.md 保留一句指向 skill，每個 session 都看得到，不只靠 description 被觸發。
- 不跑 skill-creator 的觸發測試：它用「使用者說的話」測觸發，但這個 skill 的觸發時機是 Claude 自己判斷要提問，測不準。

不和其他 skill 互相引用：

- 其他 skill 需要問使用者時只寫「詢問使用者」，不點名 ask-user。
- ask-user 的 description 也不點名是哪些 skill 在用它。
- 這樣每個 skill 都能單獨複製到別的專案，新增 skill 時也不必回頭改 ask-user。
- 代價：在 commit 審查這類長流程裡提問時，只靠 CLAUDE.md 與 description 觸發，可能忘了先載入 ask-user。

點選與問卷的界線訂在 4 題、每題 4 個選項：

- 這是 AskUserQuestion 的上限，超過就放不下。
- 原本只寫「題數多就寫問卷」，沒有數字，每次要自己猜，有時點幾下就能答完的問題也寫成問卷。

不問開放式問題：

- 給具體選項並標出建議，使用者可以只做選擇，不必自己想出答案。
- 每個選項寫出選了會怎樣，使用者不必自己推想後果。

問卷不進版控，處理完就刪除：

- 問卷只是詢問的過程。決定的結果寫進對應的文件，需要保留取捨時寫成決策紀錄。
