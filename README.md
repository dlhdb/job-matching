# 求職雷達（job-matching-agent）

自動抓取職缺與公司資訊，交由 AI 依評分邏輯打分，過濾出符合自我發展方向的職缺。

## 解決什麼問題

- 避免花大量精力在海量求職平台中人工過濾職缺。
- 了解不同產業、公司現在的發展方向。

## 快速開始

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.14，第一次使用先安裝依賴：

```bash
uv sync
```

### 我想先隨便看看有哪些職缺

用互動模式，照提示依序輸入關鍵字、縣市、頁數與職缺性質：

```bash
uv run 104/fetch_104_jobs.py
```

### 我已經知道要找什麼

用命令列模式直接指定條件，例如在台北市找全職的 Python 職缺，抓 2 頁：

```bash
uv run 104/fetch_104_jobs.py -k Python -a 台北市 -t 1 -p 2
```

### 我想一次搜尋多個相關職稱

用逗號分隔多個關鍵字，重複的職缺會自動合併：

```bash
uv run 104/fetch_104_jobs.py -k "後端工程師,Backend,Python" -a 新竹
```

縣市可以簡寫（如 `台北`），不填則搜尋全台灣。同名的市與縣會對應到清單中先出現的那個，例如 `新竹` 會視為新竹市，要搜新竹縣請寫全名。

### 我想瀏覽或分析抓到的結果

每次執行都會在 `output/104/` 產生同名的兩個檔案：

| 檔案 | 適合用途 |
| :--- | :--- |
| `jobs_104_<關鍵字>_<時間>.csv` | 用 Excel 直接開啟篩選，中文不會亂碼 |
| `jobs_104_<關鍵字>_<時間>.json` | 交給程式或 AI 做後續分析 |

各欄位的意義見 [104 爬蟲規格 §3](docs/spec/104-scraper.md#3-資料欄位對應字典-data-dictionary)，完整參數說明見 [§4](docs/spec/104-scraper.md#4-使用指南與執行範例)。

## 文件導覽

| 文件 | 內容 |
| :--- | :--- |
| [docs/prd/README.md](docs/prd/README.md) | 產品需求：目標、用例、核心技術、功能清單與狀態 |
| [docs/prd/features/](docs/prd/features/) | 各功能的需求與驗收標準 |
| [docs/spec/architecture.md](docs/spec/architecture.md) | 系統架構：程式碼地圖、資料流 |
| [docs/spec/104-scraper.md](docs/spec/104-scraper.md) | 104 爬蟲技術規格與欄位字典 |
| [docs/spec/conventions.md](docs/spec/conventions.md) | 開發慣例 |

## 使用聲明

本專案僅供個人學習與研究使用：

- 爬蟲程式已限制請求頻率，避免對目標網站造成負擔。
- 抓取到的職缺資料只存在本機（`output/` 已排除於版本控制），不會公開或轉散布。
- 職缺與公司資訊的著作權屬於原網站及刊登者。使用前請自行確認並遵守各平台的服務條款。
