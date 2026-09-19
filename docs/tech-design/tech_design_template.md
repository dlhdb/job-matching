# <功能名稱>：技術設計

<!-- 本範本在同一層複製成 <功能 ID>.md 後使用，文中相對連結可以直接沿用。
     讀者是工程師，規則見 documentation.md 的「技術設計的結構」。
     只描述已實作的現況，不標〔規劃中〕：實作前的技術方案寫在實作計畫或 commit 說明，故事完成後再更新本文件。
     判斷一段內容要不要寫：它幫工程師更快看懂全貌，或寫出讀程式碼推不出來的事嗎？兩者都不是就刪。
     以下章節沒有內容時整章省略，元件較多時可以依元件再分章。 -->

- 功能文件：[<功能 ID>.md](../features/feature_template.md)
- 程式碼：進入點與模組路徑

## 1. 總覽

讓工程師不讀程式碼，就能掌握這個功能的系統輪廓：

- 元件圖或資料流圖（mermaid）
- 每個模組一句話的職責
- 依賴方向，以及必須維持的限制與理由（例如某個模組不 import 專案內的其他模組）

範例：

```mermaid
flowchart LR
    cli["<進入點>.py"] --> core["<模組>"]
    core --> db[("data/jobs.db")]
```

- `<模組>`：一句話的職責

## 2. 流程

- 主要流程在元件之間怎麼走，寫到模組層級。
- 函式名稱只在元件之間的約定需要時才寫，例如 CLI 與 mcp-server 共用的進入點。
- 業務規則寫在功能文件，這裡用連結引用，不重寫。

## 3. 資料與儲存

- 資料表、檔案的 schema，以及設計理由。
- 誰寫、誰讀、transaction 範圍。

## 4. 外部系統整合

- 外部 API、SDK 的技術限制與坑，附上官方文件連結。
- 例如：SDK 的特殊參數、錯誤類別沒有公開匯出、傳輸層對 stdout 的限制。

## 5. 錯誤處理與結束碼

- 哪些錯誤算單筆失敗、哪些讓程式中止。
- 結束碼、stdout／stderr 的分工。

## 6. 驗收對照

- 依使用者故事分組，順序同功能文件。
- 已實作故事的每條 AC 都要有一項，反之亦然。〔規劃中〕的故事完成時再補上。
- 需要網路的條目標註〔需網路〕，測試放在 `tests/e2e/` 並加上 `@pytest.mark.network`（見 [development.md](../conventions/development.md#測試)）。
- 共用的測試資料只簡述用途，細節看測試程式。

一次跑完所有離線驗收：

```bash
uv run pytest tests/test_<模組>*.py
```

### <故事 slug>

- [AC-<slug>-<重點>](../features/feature_template.md#ac-slug-重點標題)：`uv run pytest tests/test_<模組>.py -k <函式名>`
- [AC-<slug>-real](../features/feature_template.md#ac-slug-重點標題)〔需網路〕：`uv run pytest -m network tests/e2e/test_<模組>.py -k real`
