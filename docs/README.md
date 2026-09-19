# 文件導覽 — 求職雷達

所有文件都描述系統的現況，需求或實作改變時就直接更新。文件依讀者分成三區（理由見[決策紀錄：產品文件與技術文件分目錄](conventions/decisions/product-tech-directories.md)）：

- [product/](product/)：產品文件，寫為什麼做、做什麼，讀者是 PM、設計師、架構師與工程師
  - [product/overview.md](product/overview.md)：產品總覽，包括目標與成功指標、使用者問題、非目標、使用者旅程、功能清單與現況、名詞定義
  - [product/features/](product/features/)：單一功能的功能文件，包括需求、業務規則與驗收標準，一個功能一份
  - [product/decisions/](product/decisions/)：產品取捨的決策紀錄
- [tech/](tech/)：技術文件，寫怎麼做，讀者是工程師
  - [tech/architecture.md](tech/architecture.md)：跨功能的技術總覽，包括模組依賴、資料存放與技術選型
  - [tech/tech-design/](tech/tech-design/)：單一功能的技術設計，一個功能一份，檔名與功能文件相同
  - [tech/decisions/](tech/decisions/)：技術取捨的決策紀錄
  - [tech/ai-coding-setup/](tech/ai-coding-setup/)：AI coding 工具的隔離容器與權限設定
- [conventions/](conventions/)：兩邊共用的慣例
  - [conventions/documentation.md](conventions/documentation.md)：文件撰寫慣例
  - [conventions/development.md](conventions/development.md)：開發慣例
  - [conventions/decisions/](conventions/decisions/)：文件與開發流程的決策紀錄

實作某功能時，只需讀產品總覽，加上該功能的功能文件與技術設計。

## 撰寫與使用流程

1. 新增功能或修改既有功能：
   - 新增功能：使用者能完成一件原本做不到的事時，才新增功能。
     - 在 `product/features/` 複製 [feature_template.md](product/features/feature_template.md)，依命名規則取檔名。
     - 在[功能清單](product/overview.md#功能清單)登記，狀態設為 `待規劃`。
   - 修改既有功能：下列情況都屬於修改，直接修改原本的功能文件。
     - 同一件事換個入口，例如 CLI 改成網頁
     - 擴大處理量，例如單筆改成批次
     - 只是規則或結果改變
   - 修改時，新增或修改的使用者故事標上〔規劃中〕（標記層級見 [documentation.md](conventions/documentation.md#功能文件的結構)），狀態退回 `待規劃`。
     - 此時只有〔規劃中〕的使用者故事尚未實作，該功能的「現況」維持不變。
2. 範圍外的去處：功能文件「範圍外」的每一項都要有去處。
   - 確定要做的新用法：登記到[功能清單](product/overview.md#功能清單)。
   - 小改善或技術債：記到 [TODO.md](../TODO.md)。
   - 決定不做的：寫進[非目標](product/overview.md#非目標)。
3. 定稿：「待決問題」清空後，狀態改為 `待實作`。還有待決問題的功能，不要開始實作。
4. 實作：狀態改為 `實作中`。
   - 依該使用者故事的「需求」實作，不做「範圍外」列出的事。
   - 實作時調整了業務規則，就同步更新該使用者故事的「規則」小節。
   - 技術方案寫在實作計畫或 commit 說明，不寫進技術設計。
5. 驗收：依技術設計的[驗收對照](conventions/documentation.md#技術設計的結構)，逐條執行該使用者故事的驗收，回報每條結果（✅ / ❌ 與實際輸出）。全部通過後：
   - 移除該使用者故事與共用章節中相關的〔規劃中〕標記。
   - 把會長期留下的設計更新到技術設計對應的元件章節，並在驗收對照補上新的 AC。
   - 狀態改為 `✅ 已完成`。
   - 更新該功能的[現況](product/overview.md#現況)。
