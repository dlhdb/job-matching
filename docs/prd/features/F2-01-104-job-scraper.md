# F2-01 104 職缺爬蟲

| 欄位 | 內容 |
| :--- | :--- |
| ID | F2-01 |
| 核心技術 | 2 — 從求職平台獲取職缺資訊（見 [PRD 索引](../README.md#核心技術)） |
| 狀態 | ✅ 已完成 |
| 依賴 | 無 |
| 技術規格 | [104-scraper.md](../../spec/104-scraper.md) |

## 1. 背景與目標

在 104 人力銀行網站上手動複製職缺很耗時，且搜尋結果只提供截斷的工作描述。
本功能依關鍵字與地區批量抓取 104 職缺，產出結構化資料，作為後續 AI 評分（F4）的輸入。

## 2. 使用情境

- 身為求職者，我想要輸入多個關鍵字與縣市，一次取得不重複的職缺清單，以便不必逐頁瀏覽 104。
- 身為求職者，我想要用 Excel 直接開啟結果，以便快速瀏覽與篩選。
- 身為後續的 AI 分析流程，我需要完整的工作內容與固定的欄位結構，以便穩定地評分。

## 3. 範圍

**範圍內**

- 104 搜尋 API 與職缺詳情 API
- CLI 參數模式與互動引導模式
- 輸出 CSV 與 JSON

**範圍外**

- 其他求職平台（另開 F2-xx）
- 公司評價資訊（屬 F3）
- 排程定期執行、資料庫儲存
- 跨次執行的去重（去重只在單次執行內）

## 4. 功能需求

- **FR-1**：支援以 `-k/--keyword`、`-p/--pages`、`-a/--area`、`-t/--type` 參數執行；未帶 `--keyword` 時進入互動引導模式。
- **FR-2**：多個關鍵字可用半形或全形逗號分隔，逐一搜尋。
- **FR-3**：縣市名稱可精準或模糊比對（如 `台北`）到 104 地區代碼；無法辨識或未填時搜尋全台灣。
- **FR-4**：單次執行內，以 `職缺代碼` 去重，輸出中每筆職缺唯一。
- **FR-5**：對每筆職缺呼叫詳情 API 取得完整「工作內容」與「薪資待遇」；詳情失敗時兩欄為 `null`，不以搜尋摘要回填。
- **FR-6**：輸出 CSV（`utf-8-sig` 編碼）與 JSON（UTF-8）到 `output/104/`，欄位順序固定為 `CSV_FIELDNAMES`。
- **FR-7**：請求須帶 `User-Agent` 與 `Referer` 標頭並設 `timeout`；分頁間延遲 1.0–2.0 秒、關鍵字間 2.0–3.5 秒、詳情請求前 0.1–0.3 秒。
- **FR-8**：日期欄位由 `YYYYMMDD` 轉為 `YYYY-MM-DD`；職缺與公司連結轉為完整 `https://` URL。
- **FR-9**：使用者按下 Ctrl+C 時印出取消訊息並以結束碼 0 退出。

## 5. 輸入 / 輸出契約

- **輸入**：CLI 參數或互動輸入，定義見 [104-scraper.md §4.2](../../spec/104-scraper.md)。
- **輸出**：`output/104/jobs_104_<關鍵字>_<timestamp>.csv` 與 `.json`，欄位定義見 [104-scraper.md §3](../../spec/104-scraper.md)。
- **缺值處理**：`薪資待遇`、`工作內容`、`薪資下限`、`薪資上限` 可能為 `null`，下游必須容忍。

## 6. 驗收標準

以下離線驗證都用同一段載入方式（`104/` 不是合法的 Python 套件名稱，無法直接 import）：

```python
import importlib.util as u
s = u.spec_from_file_location("f104", "104/fetch_104_jobs.py")
m = u.module_from_spec(s); s.loader.exec_module(m)
```

### AC-1：關鍵字拆分（涵蓋 FR-2）

- **Given**：關鍵字字串混用半形、全形逗號與空白
- **When**：呼叫 `parse_keywords`
- **Then**：得到去除空白後的關鍵字列表
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import importlib.util as u
  s = u.spec_from_file_location("f104", "104/fetch_104_jobs.py")
  m = u.module_from_spec(s); s.loader.exec_module(m)
  assert m.parse_keywords("Python, React，AI") == ["Python", "React", "AI"]
  print("AC-1 通過")
  EOF
  ```

  通過條件：印出 `AC-1 通過`。

### AC-2：地區解析（涵蓋 FR-3）

- **Given**：輸入精準名稱、模糊名稱、無法辨識的名稱與空值
- **When**：呼叫 `resolve_area`
- **Then**：前兩者得到正確代碼，後兩者得到 `(None, "全台灣")`
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import importlib.util as u
  s = u.spec_from_file_location("f104", "104/fetch_104_jobs.py")
  m = u.module_from_spec(s); s.loader.exec_module(m)
  assert m.resolve_area("台北市") == ("6001001000", "台北市")
  assert m.resolve_area("新竹") == ("6001006000", "新竹市")
  assert m.resolve_area("火星") == (None, "全台灣")
  assert m.resolve_area(None) == (None, "全台灣")
  print("AC-2 通過")
  EOF
  ```

  通過條件：印出 `AC-2 通過`。

### AC-3：詳情失敗時不回填（涵蓋 FR-5、FR-8）

- **Given**：詳情 API 失敗（`fetch_job_detail` 回傳 `None`）
- **When**：以含搜尋摘要的原始資料呼叫 `parse_jobs`
- **Then**：`薪資待遇`、`工作內容` 為 `None`；日期與連結已正規化
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import importlib.util as u
  s = u.spec_from_file_location("f104", "104/fetch_104_jobs.py")
  m = u.module_from_spec(s); s.loader.exec_module(m)
  m.fetch_job_detail = lambda job_id: None
  m.time.sleep = lambda sec: None
  raw = [{"jobNo": "1", "description": "摘要片段", "appearDate": "20260521",
          "link": {"job": "//www.104.com.tw/job/8s12x", "cust": "//www.104.com.tw/company/abc"}}]
  job = m.parse_jobs(raw)[0]
  assert job["薪資待遇"] is None and job["工作內容"] is None
  assert job["更新日期"] == "2026-05-21"
  assert job["職缺連結"] == "https://www.104.com.tw/job/8s12x"
  assert job["公司連結"] == "https://www.104.com.tw/company/abc"
  assert list(job) == m.CSV_FIELDNAMES
  print("AC-3 通過")
  EOF
  ```

  通過條件：印出 `AC-3 通過`。

### AC-4：請求標頭與逾時（涵蓋 FR-7）

- **Given**：程式原始碼
- **When**：檢查標頭常數與所有 `requests.get` 呼叫
- **Then**：標頭包含 `User-Agent` 與 `Referer`；每個 `requests.get` 都帶 `timeout`
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import importlib.util as u
  s = u.spec_from_file_location("f104", "104/fetch_104_jobs.py")
  m = u.module_from_spec(s); s.loader.exec_module(m)
  assert {"User-Agent", "Referer"} <= set(m.DEFAULT_HEADERS)
  print("AC-4 標頭通過")
  EOF
  grep -n "requests.get(" 104/fetch_104_jobs.py
  ```

  通過條件：印出 `AC-4 標頭通過`，且 grep 列出的每一行都含 `timeout=`。

### AC-5：實際抓取與輸出 〔需網路〕（涵蓋 FR-1、FR-4、FR-5、FR-6）

- **Given**：可連線到 104
- **When**：以重複關鍵字、1 頁、台北市執行 CLI 模式
- **Then**：`output/104/` 產生 CSV 與 JSON；職缺代碼不重複；CSV 以 BOM 開頭且表頭與 `CSV_FIELDNAMES` 一致；大多數職缺有完整工作內容
- **驗證方式**：

  ```bash
  uv run 104/fetch_104_jobs.py -k "Python,Python" -p 1 -a 台北市
  uv run python - <<'EOF'
  import csv, json, glob, os
  j = max(glob.glob("output/104/jobs_104_Python_Python_*.json"), key=os.path.getmtime)
  c = j[:-5] + ".csv"
  jobs = json.load(open(j, encoding="utf-8"))
  ids = [x["職缺代碼"] for x in jobs]
  assert jobs and len(ids) == len(set(ids)), "職缺代碼重複或無資料"
  assert open(c, "rb").read(3) == b"\xef\xbb\xbf", "CSV 缺少 BOM"
  header = next(csv.reader(open(c, encoding="utf-8-sig")))
  assert header == list(jobs[0]), "CSV 表頭與 JSON 欄位不一致"
  filled = sum(1 for x in jobs if x["工作內容"])
  print(f"AC-5 通過：{len(jobs)} 筆，{filled} 筆有工作內容")
  EOF
  ```

  通過條件：印出 `AC-5 通過`；終端輸出中第二個關鍵字的「新增去重職缺」為 0 筆；有工作內容的筆數不為 0。

### AC-6：Ctrl+C 優雅退出（涵蓋 FR-9）

- **Given**：程式處於互動模式等待輸入
- **When**：送出 SIGINT
- **Then**：印出取消訊息，結束碼為 0
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import signal, subprocess, sys, time
  p = subprocess.Popen([sys.executable, "104/fetch_104_jobs.py"],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
  time.sleep(1.5)
  p.send_signal(signal.SIGINT)
  out, _ = p.communicate(timeout=5)
  assert p.returncode == 0, p.returncode
  assert "使用者取消操作" in out
  print("AC-6 通過")
  EOF
  ```

  通過條件：印出 `AC-6 通過`。

## 7. 待決問題

無。
