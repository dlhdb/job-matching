# 具規模的修改先規劃再執行

## 決策背景與問題

AI coding 工具收到需求後常直接開始修改，等使用者看到結果時，方向不對的改動已經散在多個檔案，要花時間回退。

使用者希望具規模的修改先看到規劃、確認後才執行，小修改則照常直接做。問題是用什麼方式讓 Claude Code 做到這件事。

## 考慮過的替代方案

- 在 `.claude/settings.json` 設定 `permissions.defaultMode` 為 `plan`：
  - 由 harness 強制，plan 未核准前無法修改檔案。
  - 但每個 session 都從 plan mode 開始，連改錯字都要先核准 plan，或由使用者手動切出。
- 用 PreToolUse hook 攔下 Edit、Write：
  - hook 看不到修改的意圖，只能用改動檔案數之類的粗略門檻判斷規模。
  - 容易誤擋小修改，也容易漏掉單一檔案內的大改動。

## 最終決策

- 在 [CLAUDE.md](../../../CLAUDE.md#先規劃再執行) 列出需要先規劃的條件，符合時由 Claude Code 自行進入 plan mode，使用者核准後才執行。
- 「具規模」需要依情境判斷，只有寫成規則交給 AI 判斷，才能只在需要時觸發。代價是沒有強制力，條件寫得越具體越不容易漏。
- 影響的文件：[CLAUDE.md](../../../CLAUDE.md)。
