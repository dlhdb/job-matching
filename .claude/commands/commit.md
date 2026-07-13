---
description: 檢視已暫存的變更並產生條列式 commit message
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*)
---

檢視目前的 git 變更並協助 commit。

## 目前狀態
- 分支與狀態：!`git status -sb`
- 已暫存的變更（檔名統計）：!`git diff --cached --stat`
- 已暫存的變更（內容）：!`git diff --cached`

## 任務
1. 若沒有任何已暫存的變更，提醒使用者先 `git add`，並列出未暫存的檔案讓他挑選。
2. 依下列規範產生 commit message，**先顯示給使用者確認，不要直接 commit**（除非使用者已明確要求直接送出）：

### Commit message 規範
- 使用繁體中文。
- 首行格式：`<type>: <精簡摘要>`，type 用 Conventional Commits（feat / fix / refactor / docs / chore / test 等）；摘要盡量 ≤ 50 字元。
- 內文用條列式（`- `）描述每項修改，聚焦「做了什麼、為什麼」，不流水帳。
- 列表第一項先說明做這個改動的主要效益，後續項目才描述做了什麼。


### 格式範例
```
feat: 新增 search 節點串接外部檢索

- 新增機制以獲取即時的資訊，不只靠模型內部知識
- 在 agent/nodes/ 新增 search_node，呼叫檢索 API 取得候選文件
- graph.py 將節點接在 call_llm 之前，讓 LLM 能引用檢索結果
```

$ARGUMENTS
