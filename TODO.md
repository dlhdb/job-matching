# TODO

尚未要做、但已經確認之後要處理的事項。開始做某項時，從這裡移除，並依 CLAUDE.md 的功能開發流程進行。

## 實際使用前

- [ ] `profile/preferences.yaml` 與 `profile/experience.md` 目前是測試用的虛構資料，執行 job-scoring AC-score-real（真實評分）前要換成自己的偏好與經歷，才能判斷 AI 的理由是否與自己的判斷相符

## 評分維度（job-scoring 後續迭代）

- [ ] 通勤便利度：候選做法有依行政區分級（加上捷運標籤加分），或用地圖 API 計算實際通勤時間
- [ ] 資歷門檻：要先擴充 104-job-scraper，輸出年資要求
- [ ] 工作型態與福利（遠端、彈性工時等）：遠端資訊要先擴充爬蟲才拿得到
- [ ] 競爭程度與新鮮度（應徵人數、更新日期）：比較適合當參考資訊或篩選條件，不算進總分

## 爬蟲

- [ ] 擴充爬蟲欄位（年資要求、遠端等工作型態），供上方「資歷門檻」「工作型態與福利」維度使用

## 職缺評分（範圍外）

- [ ] 評分結果重試機制：單筆 AI 呼叫失敗時自動重打，目前單筆失敗會跳過該筆繼續，不重試
- [ ] 評分 CLI 改從職缺資料庫讀取職缺（例如 `--run-id`），目前讀爬蟲輸出的 JSON。mcp-server 的 `score_jobs` 會自行從 `run_jobs` 取職缺，所以 CLI 暫不需要
- [ ] 記錄評分使用的設定：`job_scores` 目前只存供應商與模型，看不出當時的偏好檔與經歷內容。要比較不同設定的結果時，再加一張設定表（存偏好檔與經歷全文），並讓 `job_scores` 以職缺代碼＋設定編號為主鍵，各設定的結果並存
- [ ] 保留評分歷史：`job_scores` 目前每筆職缺只留最新一次，trend-analysis 要分析分數變化時再改成多列
- [ ] `--no-cache` 強制重新呼叫 AI：目前要重問 AI 只能改動快取鍵的來源（模型、提示詞模板、經歷、`目標方向`、`產業偏好`），或刪掉 `job_scores` 中的列

## mcp-server 實作備忘

- [ ] 實作 mcp-server 時，把以下暫定的技術方案帶進實作計畫。完成後把會長期留下的部分寫成 `docs/tech/tech-design/mcp-server.md`，並從這裡移除：
  - 使用官方的 `mcp` Python SDK，以 stdio 傳輸。
  - 每個 tool 只做參數檢查與格式轉換，邏輯都呼叫既有模組（爬蟲的 `execute_scraping`、`job_scoring` 的 `score_batch`），CLI 與 MCP 的行為才會一致，之後的 Web 介面也呼叫同一組函式。
  - `score_jobs` 從 `jobs` 表讀取職缺，順序依 `run_jobs`；評分結果寫入同一個資料庫的 `job_scores`。
  - `query_jobs` 以 `jobs` LEFT JOIN `job_scores`（`職缺代碼`）取分數，沒有對應列的職缺視為未評分。
    - 排除淘汰時，未評分職缺的 `淘汰` 是 NULL，條件要寫成 `IFNULL(淘汰, 0) = 0`，才不會連未評分的職缺一起排除。
  - `get_job_detail` 的 `評分` 是 `job_scores.評分結果` 解析後的物件。
  - stdout 只留給協定（實現 FR-output）：
    - stdio 傳輸以 stdout 傳送協定訊息，任何其他輸出都會讓 client 解析失敗。
    - 爬蟲的 `execute_scraping` 會把進度與預覽表格 `print` 到 stdout。
    - tool 執行期間以 `contextlib.redirect_stdout` 把 stdout 導向 stderr，不必修改爬蟲 CLI 的輸出。
  - `score_jobs` 的進度：client 有提供 progress token 時，每筆開始時送出 MCP progress 通知。
  - tool 函式可以不經過 MCP 直接呼叫，離線測試就這樣測。
  - 驗收對照預計的測試檔是 `tests/test_mcp_server.py` 與 `tests/e2e/test_mcp_server.py`，另外要跑型別檢查 `uv run mypy src/`。

## 開發環境

- [ ] Claude Code 的自動更新在容器內無法運作：`downloads.claude.ai` 不在 [init-firewall.sh](.devcontainer/init-firewall.sh) 的白名單內，`claude doctor` 顯示 Auto-updates 為 enabled 但實際連不出去。要嘛把該網域加進白名單，要嘛改成固定版本並在重建容器時更新

## 文件

- [ ] 在 [documentation.md](docs/conventions/documentation.md#功能文件的結構) 補上「範圍外」要列哪些項目：實作者合理會以為包含、但其實不做的事（屬於相鄰功能、順手會做的下一步、刻意不採用的做法），不是列出所有沒做的事。已寫在 docs/product/overview.md「非目標」的事不重複列
