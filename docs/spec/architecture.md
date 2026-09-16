# 系統架構總覽

本文描述系統各模組之間的資料流與輸入契約；產品目標見 [docs/prd/README.md](../prd/README.md)，檔案結構見 [README.md](../../README.md#專案結構)。

目前只有 104 爬蟲一個模組，是單檔自足腳本，沒有 package 結構。第一個要長出來的模組會決定整體佈局，屆時再定架構。

## 資料流（現況）

```
104 搜尋 API ──┐
              ├─→ parse_jobs() ─→ 中文鍵名的職缺 dict ─→ CSV (utf-8-sig) + JSON
104 詳情 API ──┘
```

職缺 dict 使用**中文鍵名**（`職缺代碼`、`職缺名稱`、`工作內容`…），欄位定義見 [104-scraper.md](104-scraper.md) 第 3 節。未來的 AI 分析層應以此結構為輸入契約，並容忍其中的 `null`（詳情 API 失敗時的真實表現）。

## 資料流（規劃中）

工作評分（F1-01）會是第一個 package：`src/job_scoring/`，由 `src/score_job.py` 當作 CLI 進入點；F4 的批次工作流之後也會 import 同一個 package。

```
職缺 dict（爬蟲 JSON 中的一筆）──┐
profile/preferences.yaml ──────┼─→ 硬性淘汰 ─→ 薪資規則 ─→ LLMClient（Gemini）─→ 加權 ─→ JobScore JSON
profile/experience.md ─────────┘
```

維度、規則、提示詞與輸出欄位見 [job-scoring.md](job-scoring.md)。
