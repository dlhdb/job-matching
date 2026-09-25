# 文件不用 markdown 表格

## 決策背景與問題

文件原本大量使用 markdown 表格，功能文件表頭、使用者故事清單、欄位字典、CLI 參數、評分等級、功能清單、文件索引都是表格。

表格在原始檔中難以維護：

- 改一格就是整列的 diff，review 時看不出改了哪裡。
- 格子裡不能換行或條列，長說明（例如欄位字典中 `薪資上限` 的特殊值）只能擠在同一格。
- 型態寫成 `str | null` 時，`|` 必須跳脫成 `\|`。
- 加一欄要改每一列，中文字寬也讓原始檔無法對齊，不渲染就很難讀。

問題是文件要用什麼格式呈現這些結構化內容。

## 考慮過的替代方案

- 保留表格，只限制欄數或每格長度：
  - 規則需要人判斷「多長算太長」。
  - diff 與跳脫的問題仍在。
  - 內容一長又得改格式。
- 改用 HTML 表格：格子裡可以換行、條列，但原始檔更冗長，也更難讀。
- 每個項目各開一個標題：
  - 欄位多時標題會淹沒章節結構。
  - 會多出大量錨點。

## 最終決策

- 文件不用 markdown 表格，改用條列。
  - 各種內容的寫法見 [documentation.md「格式」](../../conventions/documentation.md#格式)。
- 真值表、判斷矩陣改寫成規則句：規則句比逐格對照更容易看出例外。
- 給 LLM 的提示詞（例如 `src/job_scoring/prompts/scoring.md`）不是文件，不受這條規則約束。
- 影響的文件：[功能文件範本](../../conventions/templates/feature.md)、所有功能文件、[docs/product/overview.md](../../product/overview.md)、[docs/tech/ai-coding-setup/](../../tech/ai-coding-setup/)、[README.md](../../../README.md)、[CLAUDE.md](../../../CLAUDE.md)。
