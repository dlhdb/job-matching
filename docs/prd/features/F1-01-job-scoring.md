# F1-01 工作評分邏輯

| 欄位 | 內容 |
| :--- | :--- |
| ID | F1-01 |
| 核心技術 | 1 — 工作評分邏輯（見 [PRD 索引](../README.md#核心技術)） |
| 狀態 | 待實作 |
| 依賴 | F2-01（使用其輸出的職缺 JSON 作為輸入） |
| 技術規格 | [job-scoring.md](../../spec/job-scoring.md) |

## 1. 背景與目標

爬蟲一次會抓到上百筆職缺，逐筆閱讀並判斷是否適合自己，要花很多時間。
本功能根據使用者提供的**工作偏好**與**工作經歷**，對單筆職缺做多維度評分，並產出總分與簡短評語，讓使用者快速判斷哪些職缺值得細看、原因是什麼（UC-02）。批次評分與排序由 F4 負責，F4 會重複使用本功能的評分函式。

## 2. 使用情境

- 身為求職者，我想要把偏好和經歷寫成檔案，以便每次評分都依照同一套標準。
- 身為求職者，我想要看到每個維度的分數與理由，以便知道總分是怎麼來的，並判斷要不要相信它。
- 身為求職者，我想要明顯不合的職缺（薪資太低、不想去的公司）直接被淘汰，以便不浪費時間與 AI 費用。
- 身為調整提示詞的開發者，我想要在不呼叫 AI 的情況下看到完整的提示詞，以便反覆修改。
- 身為後續的 F4 工作流，我需要固定格式的評分結果與可替換的 LLM 供應商，以便批次處理。

## 3. 範圍

**範圍內**

- 讀取並驗證 `profile/preferences.yaml` 與 `profile/experience.md`，並提供 `.example` 範本
- 硬性淘汰規則
- 四個評分維度：職涯方向契合度、技能匹配度、產業公司吸引力（AI 判斷），以及薪資水準（程式計算）
- 加權總分與「資料不足」判定
- 提示詞模板
- LLM 供應商抽象層與 Gemini 實作
- 對單筆職缺評分的 CLI，包含 `--dry-run`

**範圍外**（實作時不要做）

- 批次評分、結果存檔、排序與篩選（屬 F4）
- OpenAI 或其他供應商的實作（只保留介面）
- 通勤便利度、資歷門檻、工作型態與福利、競爭程度／新鮮度等維度（後續另開功能）
- 公司評價資訊（屬 F3；本功能的產業公司吸引力只看產業類別與公司名稱）
- 修改爬蟲或擴充爬蟲欄位
- 評分結果快取、重試機制

## 4. 功能需求

- **FR-1**：從指定目錄讀取 `preferences.yaml` 與 `experience.md`；`preferences.yaml` 要依 [job-scoring.md §2.1](../../spec/job-scoring.md#21-preferencesyaml-欄位字典) 驗證，缺少欄位、型別錯誤或權重的鍵不符時報錯，不補預設值。真實個人資料檔不進版控，版控中提供 `.example` 範本。
- **FR-2**：依 [§4](../../spec/job-scoring.md#4-硬性淘汰規則) 檢查硬性淘汰條件，並收集所有淘汰原因；被淘汰的職缺不呼叫 AI。
- **FR-3**：依 [§5](../../spec/job-scoring.md#5-薪資換算與計分) 換算月薪並計算薪資分數；面議、時薪、日薪、論件計酬與缺值都視為未知（`null`），不會因此被淘汰。
- **FR-4**：由 AI 依 [§3.1](../../spec/job-scoring.md#31-ai-維度的錨點描述) 的錨點，為三個 AI 維度各給 1–5 分或 `null`，每個維度都附上理由，另外提供總評；AI 回應必須通過 schema 驗證，否則視為失敗。
- **FR-5**：依 [§6](../../spec/job-scoring.md#6-總分) 計算 0–100 的加權總分；已知維度的權重不到一半時，總分為 `null`，評語標示「資料不足」。
- **FR-6**：提供 `src/score_job.py` CLI，參數與結束碼依 [§8.5](../../spec/job-scoring.md#85-cli)；`--dry-run` 只印出提示詞，不建立 LLM client。
- **FR-7**：LLM 呼叫透過 `LLMClient` 介面與 `get_client(provider, model)` 工廠函式；預設使用 Gemini。API key 讀取環境變數 `GEMINI_API_KEY`，CLI 啟動時會從專案根目錄的 `.env` 載入，但不覆寫已存在的環境變數；`.env` 不進版控，版控中提供 `.env.example`。只有 `llm.py` 可以依賴特定供應商的 SDK。

## 5. 輸入 / 輸出契約

- **輸入**：
  - 職缺：F2-01 輸出的 JSON，欄位定義見 [104-scraper.md §3](../../spec/104-scraper.md#3-資料欄位對應字典-data-dictionary)
  - 個人資料：見 [job-scoring.md §2](../../spec/job-scoring.md#2-輸入個人資料檔)
- **輸出**：`JobScore` JSON，印到 stdout，欄位定義見 [job-scoring.md §7](../../spec/job-scoring.md#7-輸出jobscore)。
- **缺值處理**：職缺欄位為 `null` 時，對應維度的分數為 `null`，並列入 `未知維度`，不猜分數；提示詞中以「（無資料）」標示缺值。

## 6. 驗收標準

### 測試資料準備

以下 AC-1 到 AC-7 都使用同一份離線測試資料，放在 `/tmp/f1-01-ac/`。先在專案根目錄執行一次：

```bash
uv run python - <<'EOF'
import json, pathlib, yaml
d = pathlib.Path("/tmp/f1-01-ac"); (d / "profile").mkdir(parents=True, exist_ok=True)
prefs = yaml.safe_load(open("profile/preferences.example.yaml", encoding="utf-8"))
prefs["目標方向"] = ["目標標記-AAA"]
prefs["薪資"] = {"期望月薪": 70000, "底線月薪": 55000, "年薪換算月數": 14}
prefs["淘汰條件"] = {"公司": ["乙公司"], "職稱關鍵字": ["業務"]}
prefs["權重"] = {"職涯方向契合度": 0.4, "技能匹配度": 0.25, "產業公司吸引力": 0.15, "薪資水準": 0.2}
yaml.safe_dump(prefs, open(d / "profile/preferences.yaml", "w", encoding="utf-8"), allow_unicode=True)
(d / "profile/experience.md").write_text("經歷標記-BBB", encoding="utf-8")
base = {"職缺代碼": "", "職缺名稱": "Python 工程師", "公司名稱": "甲公司", "產業類別": "軟體及網路相關業",
        "地區": "台北市大安區", "薪資待遇": "月薪60,000~80,000元", "薪資下限": 60000, "薪資上限": 80000,
        "更新日期": "2026-09-16", "應徵人數": 0, "工作內容": "工作標記-CCC", "電腦專長": "",
        "科系要求": "", "特色標籤": "", "職缺連結": "https://www.104.com.tw/job/x", "公司連結": "https://www.104.com.tw/company/x"}
jobs = [{**base, "職缺代碼": "ok"}, {**base, "職缺代碼": "out", "職缺名稱": "業務專員"}]
json.dump(jobs, open(d / "jobs.json", "w", encoding="utf-8"), ensure_ascii=False)
print("測試資料已建立")
EOF
```

Python 驗證片段都用 `PYTHONPATH=src` 執行，才能 import `job_scoring`。

### AC-0：型別檢查（涵蓋全部）

- **Given**：實作完成
- **When**：執行 mypy
- **Then**：沒有錯誤
- **驗證方式**：

  ```bash
  uv run mypy src/
  ```

  通過條件：輸出 `Success: no issues found`。

### AC-1：個人資料檔驗證與版控（涵蓋 FR-1、FR-6）

- **Given**：`preferences.yaml` 缺少 `權重`；另一份的 `權重` 多了一個不存在的維度
- **When**：用 `--dry-run` 執行 CLI
- **Then**：兩次都印出 `[-]` 並以 1 結束；真實個人資料檔被 git 忽略，範本則沒有被忽略
- **驗證方式**：

  ```bash
  uv run python - <<'EOF'
  import pathlib, shutil, subprocess, yaml
  src = pathlib.Path("/tmp/f1-01-ac/profile")
  good = yaml.safe_load(open(src / "preferences.yaml", encoding="utf-8"))
  cases = {"missing": {k: v for k, v in good.items() if k != "權重"},
           "badkey": {**good, "權重": {**good["權重"], "通勤便利度": 0.1}}}
  for name, prefs in cases.items():
      d = pathlib.Path(f"/tmp/f1-01-ac/{name}"); d.mkdir(exist_ok=True)
      shutil.copy(src / "experience.md", d / "experience.md")
      yaml.safe_dump(prefs, open(d / "preferences.yaml", "w", encoding="utf-8"), allow_unicode=True)
      r = subprocess.run(["uv", "run", "src/score_job.py", "--jobs", "/tmp/f1-01-ac/jobs.json",
                          "--profile-dir", str(d), "--dry-run"], capture_output=True, text=True)
      assert r.returncode == 1 and "[-]" in r.stderr, (name, r.returncode, r.stderr)
  print("AC-1 通過")
  EOF
  for f in profile/preferences.yaml profile/experience.md .env; do
      git check-ignore -q "$f" || echo "未被忽略：$f"; done
  for f in profile/preferences.example.yaml profile/experience.example.md .env.example; do
      git check-ignore -q "$f" && echo "範本被忽略：$f"; done
  ```

  通過條件：印出 `AC-1 通過`，而且沒有印出「未被忽略」或「範本被忽略」訊息。

### AC-2：薪資計分與硬性淘汰（涵蓋 FR-2、FR-3）

- **Given**：測試用偏好（期望 70,000、底線 55,000、年薪 ÷14、排除「乙公司」與「業務」）
- **When**：對各種薪資型態與淘汰條件呼叫 `score_salary`、`check_hard_filters`
- **Then**：分數與淘汰結果符合 [job-scoring.md §4–5](../../spec/job-scoring.md#4-硬性淘汰規則)
- **驗證方式**：

  ```bash
  PYTHONPATH=src uv run python - <<'EOF'
  from job_scoring.profile import load_preferences
  from job_scoring.rules import check_hard_filters, score_salary
  p = load_preferences("/tmp/f1-01-ac/profile/preferences.yaml")
  def job(s, lo, hi, name="Python 工程師", co="甲公司"):
      return {"職缺名稱": name, "公司名稱": co, "薪資待遇": s, "薪資下限": lo, "薪資上限": hi}
  cases = [  # (薪資待遇, 下限, 上限, 預期分數)
      ("月薪70,000~90,000元", 70000, 90000, 5),
      ("月薪60,000~80,000元", 60000, 80000, 4),
      ("月薪56,000~60,000元", 56000, 60000, 2),
      ("年薪980,000~1,260,000元", 980000, 1260000, 5),  # 換算 70,000~90,000
      ("月薪50,000元以上", 50000, 9999999, 2),           # 沒有上限，不淘汰
      ("待遇面議", 0, 0, None),
      ("時薪500元以上", 500, 9999999, None),
      ("論件計酬3,000~15,000元", 3000, 15000, None),
      (None, None, None, None),
  ]
  for s, lo, hi, want in cases:
      assert score_salary(job(s, lo, hi), p)[0] == want, s
      assert check_hard_filters(job(s, lo, hi), p) == [], s
  r = check_hard_filters(job("月薪40,000~50,000元", 40000, 50000), p)
  assert len(r) == 1 and "底線" in r[0], r
  r = check_hard_filters(job("年薪560,000~700,000元", 560000, 700000), p)  # 換算上限 50,000
  assert len(r) == 1 and "底線" in r[0], r
  r = check_hard_filters(job("月薪40,000~50,000元", 40000, 50000, name="業務專員", co="乙公司"), p)
  assert len(r) == 3, r  # 收集所有原因
  print("AC-2 通過")
  EOF
  ```

  通過條件：印出 `AC-2 通過`。

### AC-3：總分計算（涵蓋 FR-5）

- **Given**：權重 0.4 / 0.25 / 0.15 / 0.2
- **When**：以不同分數組合呼叫 `compute_total`
- **Then**：結果符合 [§6](../../spec/job-scoring.md#6-總分) 的公式，已知權重不到一半時為 `None`
- **驗證方式**：

  ```bash
  PYTHONPATH=src uv run python - <<'EOF'
  from job_scoring.scorer import compute_total
  w = {"職涯方向契合度": 0.4, "技能匹配度": 0.25, "產業公司吸引力": 0.15, "薪資水準": 0.2}
  def s(a, b, c, d): return dict(zip(w, [a, b, c, d]))
  assert compute_total(s(5, 5, 5, 5), w) == 100
  assert compute_total(s(1, 1, 1, 1), w) == 0
  assert compute_total(s(4, 4, 5, 4), w) == 79
  assert compute_total(s(5, 3, None, None), w) == 81     # 已知權重 0.65
  assert compute_total(s(None, None, 5, 4), w) is None   # 已知權重 0.35
  print("AC-3 通過")
  EOF
  ```

  通過條件：印出 `AC-3 通過`。

### AC-4：評分流程與 AI 回應處理（涵蓋 FR-2、FR-4、FR-5）

- **Given**：不連網的假 LLM client，回傳一個 `null` 維度；以及一份超出分數範圍的 AI 回應
- **When**：對被淘汰與沒被淘汰的職缺分別呼叫 `score_job`
- **Then**：被淘汰的職缺不呼叫 client；沒被淘汰的職缺產出正確的中文鍵名結果；超出範圍的回應無法通過驗證
- **驗證方式**：

  ```bash
  PYTHONPATH=src uv run python - <<'EOF'
  import json
  from pydantic import ValidationError
  from job_scoring.models import AIAssessment
  from job_scoring.profile import load_preferences
  from job_scoring.scorer import score_job
  p = load_preferences("/tmp/f1-01-ac/profile/preferences.yaml")
  ok, out = json.load(open("/tmp/f1-01-ac/jobs.json", encoding="utf-8"))
  reply = {"career_fit": {"score": 5, "reason": "r1"}, "skill_match": {"score": None, "reason": "r2"},
           "industry_fit": {"score": 3, "reason": "r3"}, "comment": "總評"}
  class Fake:
      calls = 0
      def assess(self, system, user):
          Fake.calls += 1
          return AIAssessment.model_validate(reply)
  r = score_job(out, p, "經歷", Fake()).model_dump(by_alias=True)
  assert Fake.calls == 0 and r["淘汰"] is True and r["維度"] is None and r["總分"] is None
  r = score_job(ok, p, "經歷", Fake()).model_dump(by_alias=True)
  assert Fake.calls == 1 and r["淘汰"] is False and r["淘汰原因"] == []
  assert list(r["維度"]) == ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準"]
  assert r["維度"]["技能匹配度"]["分數"] is None and r["維度"]["薪資水準"]["分數"] == 4
  assert r["總分"] == 83 and r["未知維度"] == ["技能匹配度"] and r["評語"] == "總評"
  bad = {**reply, "career_fit": {"score": 6, "reason": "x"}}
  try:
      AIAssessment.model_validate(bad); raise SystemExit("超出範圍的分數未被拒絕")
  except ValidationError:
      pass
  print("AC-4 通過")
  EOF
  ```

  通過條件：印出 `AC-4 通過`。

### AC-5：dry-run 印出提示詞且不建立 client（涵蓋 FR-6、FR-7）

- **Given**：`GEMINI_API_KEY` 設為空字串（模擬沒有 key；`.env` 不會覆寫已存在的變數）
- **When**：用 `--dry-run` 對沒被淘汰的職缺執行 CLI
- **Then**：結束碼為 0；輸出包含偏好、經歷、職缺內容與缺值標示。沒有 key 仍然成功，代表沒有建立 client，也沒有發出網路請求（建立 `GeminiClient` 時沒有 key 會失敗）
- **驗證方式**：

  ```bash
  GEMINI_API_KEY= uv run src/score_job.py --jobs /tmp/f1-01-ac/jobs.json --job-no ok \
      --profile-dir /tmp/f1-01-ac/profile --dry-run > /tmp/f1-01-ac/dry.txt; echo "exit=$?"
  for m in 目標標記-AAA 經歷標記-BBB 工作標記-CCC （無資料）; do grep -q "$m" /tmp/f1-01-ac/dry.txt || echo "缺少 $m"; done
  ```

  通過條件：印出 `exit=0`，而且沒有印出任何「缺少」訊息。

### AC-6：被淘汰的職缺不需要 API key（涵蓋 FR-2、FR-6）

- **Given**：`GEMINI_API_KEY` 設為空字串（模擬沒有 key；`.env` 不會覆寫已存在的變數）
- **When**：對職稱含「業務」的職缺執行 CLI（不使用 dry-run）
- **Then**：結束碼為 0，stdout 是 `淘汰: true` 的 JSON
- **驗證方式**：

  ```bash
  GEMINI_API_KEY= uv run src/score_job.py --jobs /tmp/f1-01-ac/jobs.json --job-no out \
      --profile-dir /tmp/f1-01-ac/profile > /tmp/f1-01-ac/out.json; echo "exit=$?"
  uv run python -c "import json; r=json.load(open('/tmp/f1-01-ac/out.json', encoding='utf-8')); assert r['淘汰'] and r['淘汰原因'], r; print('AC-6 通過')"
  ```

  通過條件：印出 `exit=0` 與 `AC-6 通過`。

### AC-7：錯誤處理與結束碼（涵蓋 FR-6、FR-7）

- **Given**：`GEMINI_API_KEY` 設為空字串（模擬沒有 key；`.env` 不會覆寫已存在的變數）
- **When**：(a) 對沒被淘汰的職缺評分；(b) 指定不存在的職缺代碼；(c) 以程式呼叫 `get_client` 並傳入不存在的供應商
- **Then**：(a)(b) 印出 `[-]` 並以 1 結束，(a) 的訊息提到 `GEMINI_API_KEY`；(c) 拋出例外；只有 `llm.py` import 供應商 SDK
- **驗證方式**：

  ```bash
  GEMINI_API_KEY= uv run src/score_job.py --jobs /tmp/f1-01-ac/jobs.json --job-no ok \
      --profile-dir /tmp/f1-01-ac/profile; echo "a exit=$?"
  uv run src/score_job.py --jobs /tmp/f1-01-ac/jobs.json --job-no 不存在 \
      --profile-dir /tmp/f1-01-ac/profile --dry-run; echo "b exit=$?"
  PYTHONPATH=src uv run python -c "
  from job_scoring.llm import get_client
  try: get_client('不存在', 'x'); raise SystemExit('未拋出例外')
  except ValueError: print('c 通過')"
  grep -rln "google" src/job_scoring src/score_job.py
  ```

  通過條件：(a) 的 stderr 含 `[-]` 與 `GEMINI_API_KEY`，並印出 `a exit=1`；(b) 的 stderr 含 `[-]`，並印出 `b exit=1`；印出 `c 通過`；grep 只列出 `src/job_scoring/llm.py`。

### AC-8：真實評分 〔需網路〕（涵蓋 FR-4、FR-5、FR-6）

- **Given**：已填寫 `profile/preferences.yaml` 與 `profile/experience.md`，已在 `.env` 設定 `GEMINI_API_KEY`，而且 `output/104/` 中有爬蟲結果
- **When**：對最新一份結果中第一筆有工作內容、且沒被淘汰的職缺評分
- **Then**：輸出符合 [§7](../../spec/job-scoring.md#7-輸出jobscore)；每個維度都有非空的理由；總分在 0–100 之間，或是 `null` 且評語以「資料不足」開頭
- **驗證方式**：

  ```bash
  PYTHONPATH=src uv run python - <<'EOF'
  import glob, json, os, subprocess
  from job_scoring.profile import load_preferences
  from job_scoring.rules import check_hard_filters
  f = max(glob.glob("output/104/*.json"), key=os.path.getmtime)
  p = load_preferences("profile/preferences.yaml")
  job = next(j for j in json.load(open(f, encoding="utf-8")) if j["工作內容"] and not check_hard_filters(j, p))
  out = subprocess.run(["uv", "run", "src/score_job.py", "--jobs", f, "--job-no", job["職缺代碼"]],
                       capture_output=True, text=True, check=True).stdout
  r = json.loads(out)
  assert r["職缺代碼"] == job["職缺代碼"] and r["淘汰"] is False
  assert list(r["維度"]) == ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準"]
  assert all(v["理由"].strip() for v in r["維度"].values())
  assert all(v["分數"] is None or 1 <= v["分數"] <= 5 for v in r["維度"].values())
  assert (r["總分"] is not None and 0 <= r["總分"] <= 100) or r["評語"].startswith("資料不足")
  print(json.dumps(r, ensure_ascii=False, indent=2)); print("AC-8 通過")
  EOF
  ```

  通過條件：印出 `AC-8 通過`；由使用者閱讀印出的理由，確認內容確實引用了職缺內容，且與自己的判斷大致相符。

### AC-9：缺少工作內容時不猜分數 〔需網路〕（涵蓋 FR-4、FR-5）

- **Given**：把 AC-8 的職缺改成 `工作內容` 為 null、`電腦專長` 為空字串
- **When**：執行評分
- **Then**：`技能匹配度` 為 `null` 並列在 `未知維度` 中；總分為 `null` 時，評語以「資料不足」開頭
- **驗證方式**：

  ```bash
  PYTHONPATH=src uv run python - <<'EOF'
  import glob, json, os, subprocess
  from job_scoring.profile import load_preferences
  from job_scoring.rules import check_hard_filters
  f = max(glob.glob("output/104/*.json"), key=os.path.getmtime)
  p = load_preferences("profile/preferences.yaml")
  job = next(j for j in json.load(open(f, encoding="utf-8")) if not check_hard_filters(j, p))
  job = {**job, "工作內容": None, "電腦專長": ""}
  json.dump([job], open("/tmp/f1-01-ac/nodesc.json", "w", encoding="utf-8"), ensure_ascii=False)
  r = json.loads(subprocess.run(["uv", "run", "src/score_job.py", "--jobs", "/tmp/f1-01-ac/nodesc.json"],
                                capture_output=True, text=True, check=True).stdout)
  assert r["維度"]["技能匹配度"]["分數"] is None and "技能匹配度" in r["未知維度"], r
  assert r["總分"] is not None or r["評語"].startswith("資料不足"), r
  print(json.dumps(r, ensure_ascii=False, indent=2)); print("AC-9 通過")
  EOF
  ```

  通過條件：印出 `AC-9 通過`。

## 7. 待決問題

無。
