"""
Abstract LLM Provider Interface
All providers must implement this contract.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Iterator, Any


@dataclass
class TokenUsage:
    provider: str = ""
    model: str = ""
    task_type: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    success: bool = True


@dataclass
class ProviderResponse:
    content: str = ""
    usage: Optional[TokenUsage] = None
    provider: str = ""
    model: str = ""


@dataclass
class ProviderStreamChunk:
    """Mimics LangChain AIMessageChunk for backward compatibility"""
    content: str = ""


class LLMProvider(ABC):
    """Abstract base for all LLM providers"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'huggingface', 'gemini', 'groq')"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if credentials and dependencies are present"""
        ...

    @abstractmethod
    def generate(self, messages: list, model_id: str, **kwargs) -> ProviderResponse:
        """Synchronous generation"""
        ...

    @abstractmethod
    def stream(self, messages: list, model_id: str, **kwargs) -> Iterator[ProviderStreamChunk]:
        """Streaming generation — yields ProviderStreamChunk objects"""
        ...

    def health_check(self) -> bool:
        """Quick health check (default: is_available)"""
        return self.is_available()