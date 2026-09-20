# 產品文件與技術文件分目錄

## 決策背景與問題

[功能文件與技術設計分開維護](separate-tech-design.md)之後，每個功能已經有兩份文件，但 docs/ 的目錄仍然看不出分界：

- 頂層並列產品文件（專案總覽、features/）、技術文件（architecture.md、tech-design/、ai-coding-setup/）與流程文件（conventions/）。讀者要逐一判斷哪些是寫給自己的。
- docs/README.md 同時是產品總覽、文件索引與撰寫流程。
- decisions/ 混放產品、技術與文件流程的決策，而且以流水號命名，看檔名不知道在決定什麼。
- 產品文件仍混有技術內容，例如資料庫種類與表名。目錄沒有分開，這類內容不容易被發現。

## 考慮過的替代方案

- 維持 features/ 與 tech-design/ 並列，只清理內容：
  - 單一功能的分界清楚，但頂層的 architecture.md、ai-coding-setup/、decisions/ 屬於哪一邊，仍要讀內容才知道。
  - 「產品文件不連到技術文件」只能逐檔檢查，無法用路徑判斷。
- tech/ 底下用 features/ 命名，與 product/features/ 對稱：
  - 兩個目錄同名，引用時容易連錯，「技術設計」這個名詞也對不上目錄名。
- 決策紀錄全部留在同一個 decisions/：
  - 產品文件引用決策紀錄時，看不出會不會連到技術決策。
  - 讀者要讀完內容，才知道這項取捨跟自己有沒有關係。
- 文件流程的決策（功能文件以使用者故事分章、不用表格等）硬分到 product/：
  - 這些決策同時約束技術文件，放在產品區會誤導。
  - 它們影響的是 conventions/ 的慣例，放在一起比較容易找。
- 決策紀錄保留全域流水號：
  - 分區後同一個序列散在三個目錄，看號碼無法判斷位置，號碼本身也不帶資訊。

## 最終決策

- docs/ 依讀者分成三區：
  - `product/`：產品總覽（overview.md）、功能文件（features/）、產品決策（decisions/），讀者是 PM、設計師、架構師與工程師
  - `tech/`：architecture.md、技術設計（tech-design/）、ai-coding-setup/、技術決策（decisions/），讀者是工程師
  - `conventions/`：兩邊共用的慣例，以及文件與開發流程的決策（decisions/）
- docs/README.md 只放文件索引與撰寫、使用流程。
- 依賴只有單向：`tech/` 可以連到 `product/`，`product/` 不連到 `tech/`。
- 產品文件提到資料庫時只寫「職缺資料庫」與保存了哪些資訊，不寫資料庫種類、表名、查詢方式與檔案路徑。例外是 CLI 參數說明中 `--db` 的預設值。
- 決策紀錄的檔名描述決策的目的，不用流水號。引用時連結文字寫決策標題。
- 尚未實作的功能沒有技術設計，暫定的技術方案記在 TODO.md，實作時帶進實作計畫。
- 影響的文件：
  - [docs/README.md](../../README.md)、[documentation.md](../documentation.md#文件分區)
  - 所有功能文件、技術設計與決策紀錄的路徑與相互連結
  - [architecture.md](../../tech/architecture.md)、CLAUDE.md、根目錄的 README.md 與 TODO.md
