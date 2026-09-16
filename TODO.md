# TODO

尚未要做、但已經確認之後要處理的事項。開始做某項時，從這裡移除，並依 CLAUDE.md 的功能開發流程進行。

## 待實作

- [ ] **實作 F1-01 工作評分邏輯**：依 [PRD](docs/prd/features/F1-01-job-scoring.md) 與 [規格](docs/spec/job-scoring.md) 實作
  - 新增依賴：`google-genai`、`pydantic`、`pyyaml`、`python-dotenv`（dev：`types-PyYAML`）
  - 新增範本 `profile/preferences.example.yaml`、`profile/experience.example.md`（PRD 的共用測試資料會用到）
  - 依 PRD §6 撰寫 `tests/conftest.py` 的共用 fixture，以及 `tests/test_job_scoring_*.py`、`tests/test_score_job_cli.py`
  - 目前 `profile/` 裡的是測試用的虛構資料，實際使用前要換成自己的偏好與經歷

## 文件修正

- [ ] [104-scraper.md §3](docs/spec/104-scraper.md#3-資料欄位對應字典-data-dictionary) 的「薪資上限」寫「無上限時回傳大於 9999999 的數值」，實際資料是剛好 `9999999`（例如「月薪50,000元以上」），要改成「≥ 9999999」

## 評分維度（F1-01 範圍外，之後另開功能）

- [ ] **通勤便利度**：候選做法有依行政區分級（加上捷運標籤加分），或用地圖 API 計算實際通勤時間
- [ ] **資歷門檻**：要先擴充 F2-01 爬蟲，輸出年資要求
- [ ] **工作型態與福利**（遠端、彈性工時等）：遠端資訊要先擴充爬蟲才拿得到
- [ ] **競爭程度與新鮮度**（應徵人數、更新日期）：比較適合當參考資訊或篩選條件，不算進適配分
- [ ] F3 完成後，把公司評價納入「產業公司吸引力」

## LLM

- [ ] 實作 `OpenAIClient`，並註冊到 `get_client`
