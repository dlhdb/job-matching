"""前端的 API 型別是否跟得上後端：比對 frontend/openapi.json 與 app 產生的 OpenAPI。"""

import json
from pathlib import Path

from web import create_app

OPENAPI_FILE = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def test_create_app_openapi_matches_generated_file(tmp_path):
    generated = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))

    assert create_app(tmp_path / "jobs.db").openapi() == generated, (
        "frontend/openapi.json 不是最新的，執行 scripts/gen-api-types.sh 重新產生"
    )
