"""工作評分 LLM 抽象層的測試：以假的 SDK client 驗證 GeminiClient 的請求與錯誤處理，不連網；另檢查供應商 SDK 的隔離與 API key 的版控。"""

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from job_scoring import llm
from job_scoring.models import AIAssessment

PROJECT_ROOT = Path(__file__).resolve().parents[1]

VALID_RESPONSE = (
    '{"career_fit": {"score": 4, "reason": "a"}, "skill_match": {"score": null, "reason": "b"},'
    ' "industry_fit": {"score": 5, "reason": "c"}, "comment": "總評"}'
)


@pytest.fixture
def fake_sdk(monkeypatch):
    """
    以假物件取代 genai.Client，記錄 interactions.create 的參數

    :return: callable, fake_sdk(result) -> list[dict]；result 為回應文字、None（無文字）或例外
    """
    def _install(result):
        calls = []

        def _create(**kwargs):
            calls.append(kwargs)
            if isinstance(result, Exception):
                raise result
            return SimpleNamespace(output_text=result, status="completed")

        fake = SimpleNamespace(interactions=SimpleNamespace(create=_create))
        monkeypatch.setattr(llm.genai, "Client", lambda api_key: fake)
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        return calls
    return _install


def test_gemini_client_assess_request(fake_sdk):
    calls = fake_sdk(VALID_RESPONSE)

    result = llm.GeminiClient("gemini-3.8-flash").assess("系統", "使用者")

    assert result.skill_match.score is None
    request = calls[0]
    assert request["model"] == "gemini-3.8-flash"
    assert request["input"] == "使用者"
    assert request["system_instruction"] == "系統"
    assert request["response_format"]["schema_"] == AIAssessment.model_json_schema()
    assert request["store"] is False
    assert request["timeout"]


def test_gemini_client_wraps_sdk_error(fake_sdk):
    fake_sdk(ConnectionError("boom"))

    with pytest.raises(llm.LLMError):
        llm.GeminiClient("m").assess("s", "u")


def test_gemini_client_empty_output(fake_sdk):
    fake_sdk(None)

    with pytest.raises(llm.LLMError):
        llm.GeminiClient("m").assess("s", "u")


def test_gemini_client_invalid_schema(fake_sdk):
    fake_sdk('{"career_fit": {"score": 6, "reason": "a"}}')

    with pytest.raises(ValidationError):
        llm.GeminiClient("m").assess("s", "u")


def test_get_client_gemini_requires_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY"):
        llm.get_client("gemini", "m")


def _imported_modules(path):
    """
    列出一個 Python 檔 import 的模組名稱

    :return: Iterator[str]
    """
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_provider_sdk_isolated_to_llm():
    files = sorted((PROJECT_ROOT / "src" / "job_scoring").glob("*.py"))
    importing_google = {
        path.name for path in files
        if any(name == "google" or name.startswith("google.") for name in _imported_modules(path))
    }

    assert importing_google == {"llm.py"}


def _is_ignored(path):
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT, check=False)
    return result.returncode == 0


def test_llm_env_ignored_and_example_tracked():
    assert _is_ignored(".env")
    assert not _is_ignored(".env.example")
    assert (PROJECT_ROOT / ".env.example").is_file()
