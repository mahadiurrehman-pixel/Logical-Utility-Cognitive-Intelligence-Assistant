"""
Groq Provider (LPU — Ultra-fast inference)
"""
from typing import Iterator
from providers.base import LLMProvider, ProviderResponse, ProviderStreamChunk, TokenUsage
from llm_config import CREDENTIALS


class GroqProvider(LLMProvider):

    @property
    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return bool(CREDENTIALS.get("groq"))

    def _get_chat_model(self, model_id: str):
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_id,
            api_key=CREDENTIALS["groq"],
            temperature=0.7,
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
            if content:
                yield ProviderStreamChunk(content=str(content))