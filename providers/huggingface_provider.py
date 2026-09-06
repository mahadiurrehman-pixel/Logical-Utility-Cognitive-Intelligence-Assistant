"""
Hugging Face Inference API Provider

Supports:
- Qwen
- DeepSeek
- Llama
- Mistral
- Other compatible Hugging Face Inference models

Architecture:
- Non-streaming: LangChain ChatHuggingFace
- Streaming: Hugging Face InferenceClient

The public provider interface remains unchanged.
"""

from typing import Iterator, Any

from huggingface_hub import InferenceClient

from providers.base import (
    LLMProvider,
    ProviderResponse,
    ProviderStreamChunk,
    TokenUsage,
)

from llm_config import CREDENTIALS


class HuggingFaceProvider(LLMProvider):

    # ========================================================
    # PROVIDER NAME
    # ========================================================

    @property
    def name(self) -> str:
        return "huggingface"

    # ========================================================
    # AVAILABILITY
    # ========================================================

    def is_available(self) -> bool:
        """
        Return True when a Hugging Face token is configured.
        """

        return bool(
            CREDENTIALS.get("huggingface")
        )

    # ========================================================
    # CLIENT
    # ========================================================

    def _get_client(self) -> InferenceClient:
        """
        Create a Hugging Face InferenceClient.
        """

        token = CREDENTIALS.get("huggingface")

        if not token:
            raise RuntimeError(
                "Hugging Face token is not configured."
            )

        return InferenceClient(
            token=token,
        )

    # ========================================================
    # LANGCHAIN CHAT MODEL
    # ========================================================

    def _get_chat_model(self, model_id: str):
        """
        Create LangChain Hugging Face chat model.

        Used for non-streaming generation.
        """

        from langchain_huggingface import (
            ChatHuggingFace,
            HuggingFaceEndpoint,
        )

        token = CREDENTIALS.get("huggingface")

        if not token:
            raise RuntimeError(
                "Hugging Face token is not configured."
            )

        llm = HuggingFaceEndpoint(
            repo_id=model_id,
            task="text-generation",
            huggingfacehub_api_token=token,
            max_new_tokens=1024,
            temperature=0.7,
        )

        return ChatHuggingFace(
            llm=llm
        )

    # ========================================================
    # CONTENT NORMALIZATION
    # ========================================================

    def _normalize_content(
        self,
        content: Any,
    ) -> str:
        """
        Convert any supported message content into plain text.

        Hugging Face chat completion expects normal text
        content for this provider path.
        """

        if content is None:
            return ""

        # --------------------------------------------
        # Normal string
        # --------------------------------------------

        if isinstance(content, str):
            return content

        # --------------------------------------------
        # Structured/list content
        # --------------------------------------------

        if isinstance(content, list):

            parts = []

            for item in content:

                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):

                    text = item.get("text")

                    if text is not None:
                        parts.append(str(text))
                        continue

                    value = item.get("content")

                    if value is not None:
                        parts.append(str(value))
                        continue

                parts.append(str(item))

            return "\n".join(parts)

        # --------------------------------------------
        # Other types
        # --------------------------------------------

        return str(content)

    # ========================================================
    # MESSAGE NORMALIZATION
    # ========================================================

    def _normalize_messages(
        self,
        messages: list,
    ) -> list:
        """
        Convert LangChain/LUCIA messages into simple
        Hugging Face-compatible dictionaries.
        """

        normalized = []

        role_map = {
            "human": "user",
            "user": "user",
            "ai": "assistant",
            "assistant": "assistant",
            "system": "system",
            "tool": "tool",
        }

        for message in messages:

            # --------------------------------------------
            # LangChain message object
            # --------------------------------------------

            if hasattr(message, "type") and hasattr(
                message,
                "content",
            ):

                raw_role = getattr(
                    message,
                    "type",
                    "user",
                )

                role = role_map.get(
                    raw_role,
                    "user",
                )

                content = self._normalize_content(
                    getattr(
                        message,
                        "content",
                        "",
                    )
                )

                normalized.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

                continue

            # --------------------------------------------
            # Dictionary message
            # --------------------------------------------

            if isinstance(message, dict):

                raw_role = message.get(
                    "role",
                    "user",
                )

                role = role_map.get(
                    raw_role,
                    "user",
                )

                content = self._normalize_content(
                    message.get(
                        "content",
                        "",
                    )
                )

                normalized.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

                continue

            # --------------------------------------------
            # Unknown message type
            # --------------------------------------------

            normalized.append(
                {
                    "role": "user",
                    "content": str(message),
                }
            )

        return normalized

    # ========================================================
    # NORMAL GENERATION
    # ========================================================

    def generate(
        self,
        messages: list,
        model_id: str,
        **kwargs,
    ) -> ProviderResponse:
        """
        Generate a complete response.

        Uses LangChain ChatHuggingFace.
        """

        chat = self._get_chat_model(
            model_id
        )

        response = chat.invoke(
            messages
        )

        # --------------------------------------------
        # Usage metadata
        # --------------------------------------------

        usage_metadata = getattr(
            response,
            "usage_metadata",
            None,
        )

        if not isinstance(
            usage_metadata,
            dict,
        ):
            usage_metadata = {}

        input_tokens = usage_metadata.get(
            "input_tokens"
        )

        output_tokens = usage_metadata.get(
            "output_tokens"
        )

        total_tokens = usage_metadata.get(
            "total_tokens"
        )

        # --------------------------------------------
        # Provider response
        # --------------------------------------------

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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
        )

    # ========================================================
    # STREAMING
    # ========================================================

    def stream(
        self,
        messages: list,
        model_id: str,
        **kwargs,
    ) -> Iterator[ProviderStreamChunk]:
        """
        Stream directly through Hugging Face InferenceClient.

        ChatHuggingFace.stream() is intentionally not used.
        """

        client = self._get_client()

        # --------------------------------------------
        # Normalize messages
        # --------------------------------------------

        normalized_messages = self._normalize_messages(
            messages
        )

        # ====================================================
        # DEBUG
        # ====================================================
        #
        # We intentionally DON'T print the actual message
        # contents because they may contain private memories
        # or conversation data.
        #
        # This only shows the structure being sent to HF.
        # ====================================================

        print("\n========== HF DEBUG ==========")

        print(
            "MODEL:",
            model_id
        )

        print(
            "MESSAGE COUNT:",
            len(normalized_messages)
        )

        for index, message in enumerate(
            normalized_messages
        ):

            role = message.get(
                "role"
            )

            content = message.get(
                "content",
                "",
            )

            print(
                f"[{index}] "
                f"role={role} "
                f"content_type={type(content).__name__} "
                f"content_length={len(content)}"
            )

        print(
            "==============================\n"
        )

        # ====================================================
        # DIRECT HF STREAMING REQUEST
        # ====================================================
        #
        # Keep this intentionally minimal.
        #
        # No:
        # - temperature
        # - max_tokens
        # - max_new_tokens
        # - extra generation parameters
        #
        # This matches the standalone HF streaming test
        # that was verified to work.
        # ====================================================

        stream_response = client.chat_completion(
            model=model_id,
            messages=normalized_messages,
            stream=True,
        )

        # ====================================================
        # PROCESS STREAM
        # ====================================================

        for chunk in stream_response:

            if not chunk.choices:
                continue

            content = chunk.choices[0].delta.content

            if not content:
                continue

            yield ProviderStreamChunk(
                content=content
            )