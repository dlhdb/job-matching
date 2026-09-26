#!/bin/sh
# 從 FastAPI 的 OpenAPI 產生前端的 API 型別，前後端的欄位才一致。
# 改了 API 的路徑或回應模型後執行；frontend/openapi.json 與 frontend/src/api/schema.d.ts 都進版控，
# tests/test_web_openapi.py 會檢查 openapi.json 是否是最新的。
set -eu

cd "$(git rev-parse --show-toplevel)"

echo "⏳ 產生 frontend/openapi.json"
# 只讀 app 的定義，不會開啟資料庫
uv run --no-sync python -c '
import json, sys
sys.path.insert(0, "src")
from web import create_app
json.dump(create_app("unused.db").openapi(), sys.stdout, ensure_ascii=False, indent=2)
print()
' > frontend/openapi.json

echo "⏳ 產生 frontend/src/api/schema.d.ts"
mkdir -p frontend/src/api
npm exec --prefix frontend -- openapi-typescript frontend/openapi.json -o frontend/src/api/schema.d.ts

echo "🎉 API 型別已更新"
