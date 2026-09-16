"""
LLM 供應商抽象層（job-scoring.md §8.4）。

只有本模組可以依賴特定供應商的 SDK；其他模組只透過 LLMClient 介面與 get_client() 使用 LLM。
"""

import os
from typing import Callable, Protocol

from google import genai

from job_scoring.models import AIAssessment

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.8-flash"
API_KEY_ENV = "GEMINI_API_KEY"
# 單次 LLM 請求的逾時秒數
REQUEST_TIMEOUT = 120


class LLMError(RuntimeError):
    """建立 client 或呼叫 LLM 失敗（缺少 API key、網路或 API 錯誤、回應為空）"""


class LLMClient(Protocol):
    def assess(self, system: str, user: str) -> AIAssessment:
        """
        請 LLM 依提示詞評分。

        :param system: str, system 提示詞
        :param user: str, user 提示詞
        :return: AIAssessment, 通過 schema 驗證的評分結果
        :raises LLMError: 呼叫失敗
        :raises pydantic.ValidationError: 回應不符合 schema
        """
        ...


class GeminiClient:
    """以 google-genai 的 Interactions API 呼叫 Gemini"""

    def __init__(self, model: str) -> None:
        """
        建立 Gemini client；API key 從環境變數讀取。

        :param model: str, 模型名稱，例如 gemini-3.8-flash
        :raises LLMError: 沒有設定 GEMINI_API_KEY 或值為空字串
        """
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise LLMError(f"未設定環境變數 {API_KEY_ENV}，請在專案根目錄的 .env 填入（範本見 .env.example）")
        self.model = model
        self._client = genai.Client(api_key=api_key)

    def assess(self, system: str, user: str) -> AIAssessment:
        """
        以 structured output 要求 JSON 回應，再以 AIAssessment 驗證。

        Gemini 3.8 Flash 已不支援 temperature，因此不設定取樣參數。
        store=False：提示詞含個人經歷，不在伺服器端保存互動紀錄。

        :param system: str, system 提示詞
        :param user: str, user 提示詞
        :return: AIAssessment, 通過 schema 驗證的評分結果
        :raises LLMError: API 呼叫失敗或回應沒有文字
        :raises pydantic.ValidationError: 回應不符合 schema
        """
        try:
            interaction = self._client.interactions.create(
                model=self.model,
                input=user,
                system_instruction=system,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    # SDK 的 TypedDict 鍵名是 schema_，送出時會序列化成 API 的 schema
                    "schema_": AIAssessment.model_json_schema(),
                },
                store=False,
                stream=False,
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            # Interactions API 的錯誤類別（HTTP 錯誤、連線錯誤、逾時）沒有公開匯出，
            # try 區塊內只有 SDK 呼叫，因此在這個範圍內統一轉成 LLMError
            raise LLMError(f"Gemini API 呼叫失敗（{type(e).__name__}）：{e}") from e

        # stream=False 一定回傳 Interaction，但 SDK 標註的回傳型別是與串流的聯集，因此以 getattr 取值
        output_text = getattr(interaction, "output_text", None)
        if not output_text:
            status = getattr(interaction, "status", None)
            raise LLMError(f"Gemini 沒有回傳文字（status: {status}）")
        return AIAssessment.model_validate_json(output_text)


# 供應商名稱 → client 建構函式；新增供應商時只要註冊到這裡
_PROVIDERS: dict[str, Callable[[str], LLMClient]] = {
    "gemini": GeminiClient,
}


def get_client(provider: str, model: str) -> LLMClient:
    """
    依供應商名稱建立 LLM client。

    :param provider: str, 供應商名稱，例如 gemini
    :param model: str, 模型名稱
    :return: LLMClient, 對應的 client
    :raises ValueError: 不認得的供應商名稱
    :raises LLMError: client 建立失敗（例如缺少 API key）
    """
    factory = _PROVIDERS.get(provider)
    if factory is None:
        raise ValueError(f"不支援的 LLM 供應商：{provider}（可用：{', '.join(_PROVIDERS)}）")
    return factory(model)
