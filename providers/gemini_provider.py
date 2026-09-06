"""
Google Gemini Provider
"""
from typing import Iterator
from providers.base import LLMProvider, ProviderResponse, ProviderStreamChunk, TokenUsage
from llm_config import CREDENTIALS


class GeminiProvider(LLMProvider):

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        return bool(CREDENTIALS.get("gemini"))

    def _get_chat_model(self, model_id: str):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=CREDENTIALS["gemini"],
            streaming=True,
        )

    def generate(self, messages: list, model_id: str, **kwargs) -> ProviderResponse:
        chat = self._get_chat_model(model_id)
        response = chat.invoke(messages)
        usage_meta = getattr(response, "usage_metadata", None) or {}
        return ProviderResponse(
            content=response.content,
            provider=self.name,
            model=model_id,
            usage=TokenUsage(
                provider=self.name,
                model=model_id,
                task_type=kwargs.get("task_type", "chat"),
                input_tokens=usage_meta.get("input_tokens"),
                output_tokens=usage_meta.get("output_tokens"),
                total_tokens=usage_meta.get("total_tokens"),
            )
        )

    def stream(self, messages: list, model_id: str, **kwargs) -> Iterator[ProviderStreamChunk]:
        chat = self._get_chat_model(model_id)
        for chunk in chat.stream(messages):
            content = chunk.content if hasattr(chunk, "content") else ""
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        yield ProviderStreamChunk(content=str(item["text"]))
                    elif isinstance(item, str):
                        yield ProviderStreamChunk(content=item)
            elif content:
                yield ProviderStreamChunk(content=str(content))