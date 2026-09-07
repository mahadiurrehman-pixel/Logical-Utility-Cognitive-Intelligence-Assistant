
"""
LUCIA Groq Provider Adapter

Supports multiple independent Groq credentials:

- groq_primary
- groq_mdi
- groq_uni

Each instance has its own API key and provider identity.
"""

from typing import Iterator

from providers.base import (
    LLMProvider,
    ProviderResponse,
    ProviderStreamChunk,
    TokenUsage,
)

from llm_config import CREDENTIALS


class GroqProvider(LLMProvider):

    def __init__(
        self,
        provider_id: str = "groq_primary",
    ):
        self.provider_id = provider_id

    # ========================================================
    # PROVIDER IDENTITY
    # ========================================================

    @property
    def name(self) -> str:
        """
        Logical provider name used by the gateway.

        Example:
            groq_primary
            groq_mdi
            groq_uni
        """
        return self.provider_id

    # ========================================================
    # CREDENTIAL
    # ========================================================

    def _get_api_key(self) -> str:
        """
        Return API key for this specific Groq account.
        """

        return CREDENTIALS.get(
            self.provider_id,
            "",
        )

    # ========================================================
    # AVAILABILITY
    # ========================================================

    def is_available(self) -> bool:
        """
        Provider is available only when its
        specific credential exists.
        """

        return bool(
            self._get_api_key()
        )

    # ========================================================
    # CHAT MODEL
    # ========================================================

    def _get_chat_model(
        self,
        model_id: str,
    ):
        """
        Create a ChatGroq instance using
        this provider's own API key.
        """

        from langchain_groq import ChatGroq

        api_key = self._get_api_key()

        if not api_key:
            raise RuntimeError(
                f"No API key configured for {self.provider_id}"
            )

        return ChatGroq(
            model=model_id,
            api_key=api_key,
            temperature=0.7,
            streaming=True,
        )

    # ========================================================
    # GENERATE
    # ========================================================

    def generate(
        self,
        messages: list,
        model_id: str,
        **kwargs,
    ) -> ProviderResponse:

        chat = self._get_chat_model(
            model_id
        )

        response = chat.invoke(messages)

        usage_meta = (
            getattr(
                response,
                "usage_metadata",
                None,
            )
            or {}
        )

        return ProviderResponse(
            content=response.content,

            provider=self.name,

            model=model_id,

            usage=TokenUsage(
                provider=self.name,
                model=model_id,
                task_type=kwargs.get(
                    "task_type",
                    "chat",
                ),
                input_tokens=usage_meta.get(
                    "input_tokens"
                ),
                output_tokens=usage_meta.get(
                    "output_tokens"
                ),
                total_tokens=usage_meta.get(
                    "total_tokens"
                ),
            ),
        )

    # ========================================================
    # STREAM
    # ========================================================

    def stream(
        self,
        messages: list,
        model_id: str,
        **kwargs,
    ) -> Iterator[ProviderStreamChunk]:

        chat = self._get_chat_model(
            model_id
        )

        for chunk in chat.stream(messages):

            content = (
                chunk.content
                if hasattr(chunk, "content")
                else ""
            )

            if content:

                yield ProviderStreamChunk(
                    content=str(content)
                )

