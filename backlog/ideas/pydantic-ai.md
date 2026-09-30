# 改用 Pydantic AI 驗證 AI 回應

想解決什麼見 [TODO.md](../TODO.md#改用-pydantic-ai-驗證-ai-回應)。

## 驗證與重打不需要 Pydantic AI

Pydantic AI 在驗證 AI 回應上提供的功能，不換框架也做得到。

已經實作的：

- 格式、分數範圍、理由與總評不可空白：`AIAssessment` 的 Pydantic validator。
- 驗證不過時重打 1 次，並把錯誤告訴 AI：`scorer._assess` 與 `prompt.retry_feedback`，所有供應商共用。

還沒實作、但不需要 Pydantic AI 的：

- 內容層級的檢查，例如理由要引用職缺內容、分數和理由不矛盾：
  - 可以用 Pydantic validator 加上 validation context（驗證時傳入職缺內容）來寫。
  - 難的是判斷規則本身，換框架一樣要自己寫。

## 各觸發條件為什麼需要 Pydantic AI

觸發條件見 [TODO.md 的「怎麼決定」](../TODO.md#改用-pydantic-ai-驗證-ai-回應)，這裡寫各自的理由：

- 評分時讓 AI 自己查資料：
  - 例如查公司資訊、同職位的薪資行情。
  - 專案目標本來就包含公司資訊。
  - 自己寫的話，要處理工具定義、解析 AI 的工具呼叫、把結果回填給 AI、限制呼叫次數。
  - 這是 Pydantic AI 的主要用途。
- 接第二家 AI 供應商：
  - 每家的 structured output 寫法、錯誤類別、可用的參數都不同，現在每接一家都要另寫一個 client。
  - Pydantic AI 換模型只要改一個字串。
  - 功能文件目前把 Gemini 以外的供應商列在範圍外，要先改範圍。
- 評分變成多步驟：
  - 例如先摘要職缺再評分，或每個維度各問一次。
  - 要串接多次呼叫、傳遞中間結果，每一步各自驗證與重打。

## 試用時要確認的事

試用 Pydantic AI 接 Gemini，逐項確認。前三項任一項做不到就不採用：

1. 不保存互動紀錄：
   - 提示詞含個人經歷，功能文件規定呼叫 AI 時要求供應商不保存互動紀錄（見 [job-auto-scoring 的非功能需求規則](../../docs/product/features/job-auto-scoring.md#122-規則)）。
   - 現在用 Gemini 的 Interactions API 並設定 `store=False`。
   - 要確認 Pydantic AI 的 Gemini 支援走哪個 API，能不能做到同樣的事。
2. 重打規則照舊（見 [job-auto-scoring 的 AI 回應的檢查](../../docs/product/features/job-auto-scoring.md#429-ai-回應的檢查)）：
   - 驗證不過時最多重打 1 次。
   - 附給 AI 的錯誤照現在的寫法：中文說明、不附完整回應、錯誤不屬於任何欄位時不附內容。
   - API 錯誤不重打：SDK 已經重試過暫時性的錯誤。
3. 評分依據對得上：
   - 評分依據的提示詞由模板與職缺快照組回（見 [job-auto-scoring 的顯示評分依據](../../docs/product/features/job-auto-scoring.md#1122-顯示評分依據)）。
   - 標準和現在一致：
     - 評分用的資料與判斷方式要和評分依據相同。
     - 只說明輸出格式的附加文字可以不記錄。現在重打時附加的錯誤說明就不記錄，因為評分用的資料沒變。
   - Pydantic AI 若自行加上指示，例如以工具呼叫取得結構化輸出時附的工具說明：
     - 只說明輸出格式時，照現在的標準可以不記錄。
     - 會影響 AI 怎麼判斷時，要能關掉，或改成把加上的內容也記下來。
4. 結構化輸出：
   - 能沿用 `AIAssessment` 當輸出型別，自己寫的 validator 照樣生效。
   - Pydantic AI 預設以工具呼叫取得結構化輸出，要確認能改用 Gemini 原生的 structured output。
   - 支援所有可以選的模型（`llm.MODELS`，目前是 `gemini-3.8-flash` 與 `gemini-3.1-pro-preview`），每個都要試。
   - 不送模型不支援的取樣參數，例如 `gemini-3.8-flash` 不支援 `temperature`。
5. 錯誤對應：
   - 例外分得出 API 錯誤與回應不能用。
   - 失敗原因照樣顯示在列上，單筆失敗不中斷整批。
6. 測試：
   - 現在用假的 LLM client 離線測試。
   - Pydantic AI 有 `TestModel`、`FunctionModel` 可以代替真的模型，看測試要改寫多少。
7. 依賴：
   - 套件的大小與改版速度，文件網址已經搬過一次。
   - 要固定版本，升級時重新確認上面各項。
8. 改動量：
   - `llm.py`、`scorer._assess`、`prompt.retry_feedback` 能拿掉多少。
   - `tests/` 要改多少。
