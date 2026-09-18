# TODO

尚未要做、但已經確認之後要處理的事項。開始做某項時，從這裡移除，並依 CLAUDE.md 的功能開發流程進行。

## 實際使用前

- [ ] `profile/preferences.yaml` 與 `profile/experience.md` 目前是測試用的虛構資料，執行 job-scoring AC-score-real（真實評分）前要換成自己的偏好與經歷，才能判斷 AI 的理由是否與自己的判斷相符

## 評分維度（job-scoring 後續迭代）

- [ ] **通勤便利度**：候選做法有依行政區分級（加上捷運標籤加分），或用地圖 API 計算實際通勤時間
- [ ] **資歷門檻**：要先擴充 104-job-scraper，輸出年資要求
- [ ] **工作型態與福利**（遠端、彈性工時等）：遠端資訊要先擴充爬蟲才拿得到
- [ ] **競爭程度與新鮮度**（應徵人數、更新日期）：比較適合當參考資訊或篩選條件，不算進總分
- [ ] company-info 完成後，把公司評價納入「產業公司吸引力」

## 爬蟲

- [ ] 擴充爬蟲欄位（年資要求、遠端等工作型態），供上方「資歷門檻」「工作型態與福利」維度使用

## 職缺評分（範圍外）

- [ ] 評分結果重試機制：單筆 AI 呼叫失敗時自動重打，目前單筆失敗會跳過該筆繼續，不重試
- [ ] 評分 CLI 改從職缺資料庫讀取職缺（例如 `--run-id`），目前讀爬蟲輸出的 JSON。mcp-server 的 `score_jobs` 會自行從 `run_jobs` 取職缺，所以 CLI 暫不需要
- [ ] 記錄評分使用的設定：`job_scores` 目前只存供應商與模型，看不出當時的偏好檔與經歷內容。要比較不同設定的結果時，再加一張設定表（存偏好檔與經歷全文），並讓 `job_scores` 以職缺代碼＋設定編號為主鍵，各設定的結果並存
- [ ] 保留評分歷史：`job_scores` 目前每筆職缺只留最新一次，trend-analysis 要分析分數變化時再改成多列
- [ ] `--no-cache` 強制重新呼叫 AI：目前要重問 AI 只能改動快取鍵的來源（模型、提示詞模板、經歷、`目標方向`、`產業偏好`），或刪掉 `job_scores` 中的列
- [ ] company-info（擷取公司資訊與評價）完成後，擴充 job-scoring 支援公司評分

## 產品

- [ ] trend-analysis 規劃時，訂定第二個產品目標「了解不同產業、公司現在的發展方向」的成功指標（見 [docs/README.md](docs/README.md#成功指標)）

## LLM

- [ ] 實作 `OpenAIClient`，並註冊到 `get_client`

## 文件

- [ ] [README.md](README.md) 的「文件導覽」缺 mcp-server，加一列指到 [docs/features/mcp-server.md](docs/features/mcp-server.md)
- [ ] 104-job-scraper、job-database、mcp-server 改成使用者故事結構（見 [conventions.md](docs/conventions.md#功能文件的結構)），並補上「非功能需求」一章：目前只有 job-scoring 遷移過，這三份還是「需求／設計／驗收」各一章、FR／AC 用流水號，AC 標題也還列著「涵蓋 FR-…」。mcp-server 引用 job-database 的 `FR-1`，遷移時一併改成描述加章節連結。等 job-scoring 的新結構實際用過一輪、確認好讀再遷
