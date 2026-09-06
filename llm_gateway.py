"""
LUCIA LLM Gateway
Central routing, retry, health tracking, logging, and streaming engine.
All LLM calls go through this single gateway.
"""
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Iterator, Optional, List, Dict, Any
from dataclasses import dataclass, field

from llm_config import (
    PROVIDER_PRIORITY, MODELS, RETRY_CONFIG, COOLDOWN_CONFIG,
    DEFAULT_TASK_TYPE, CREDENTIALS
)
from providers.base import LLMProvider, ProviderResponse, ProviderStreamChunk, TokenUsage
from providers.huggingface_provider import HuggingFaceProvider
from providers.gemini_provider import GeminiProvider
from providers.groq_provider import GroqProvider

# ==========================================
# LOGGING SETUP
# ==========================================
logger = logging.getLogger("lucia.gateway")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s | %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)


# ==========================================
# ERROR CLASSIFICATION
# ==========================================
class GatewayError(Exception):
    """Base gateway error"""
    pass

class TransientProviderError(GatewayError):
    pass

class RateLimitError(TransientProviderError):
    pass

class AuthenticationError(GatewayError):
    pass

class InvalidRequestError(GatewayError):
    pass

class ProviderUnavailableError(TransientProviderError):
    pass

class TimeoutError(TransientProviderError):
    pass

class PermanentProviderError(GatewayError):
    pass


def classify_error(error: Exception) -> GatewayError:
    """Classify raw exceptions into gateway error categories"""
    err_str = str(error).lower()
    
    if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
        return RateLimitError(str(error))
    if "401" in err_str or "403" in err_str or "invalid api key" in err_str or "authentication" in err_str or "unauthorized" in err_str:
        return AuthenticationError(str(error))
    if "timeout" in err_str or "timed out" in err_str:
        return TimeoutError(str(error))
    if "500" in err_str or "502" in err_str or "503" in err_str or "504" in err_str or "unavailable" in err_str:
        return ProviderUnavailableError(str(error))
    if "400" in err_str or "invalid request" in err_str or "bad request" in err_str:
        return InvalidRequestError(str(error))
    
    return TransientProviderError(str(error))


# ==========================================
# PROVIDER HEALTH TRACKER
# ==========================================
@dataclass
class ProviderHealth:
    status: str = "HEALTHY"          # HEALTHY | COOLDOWN | DISABLED
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    last_success: Optional[datetime] = None


# ==========================================
# TOKEN USAGE TRACKER
# ==========================================
@dataclass
class UsageRecord:
    provider: str
    model: str
    task_type: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    timestamp: str
    success: bool


# ==========================================
# LLM GATEWAY
# ==========================================
class LLMGateway:
    """
    Central LLM Gateway with multi-provider routing, retry, health, and streaming.
    Drop-in replacement for LangChain ChatModel (.invoke and .stream).
    """

    def __init__(self):
        # Initialize all providers
        self._providers: Dict[str, LLMProvider] = {
            "huggingface": HuggingFaceProvider(),
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
        }
        
        # Health state
        self._health: Dict[str, ProviderHealth] = {
            name: ProviderHealth() for name in self._providers
        }
        
        # Usage log (in-memory, last 100 records)
        self._usage_log: List[UsageRecord] = []
        self._max_usage_records = 100

    # ==========================================
    # PUBLIC INTERFACE (Backward Compatible)
    # ==========================================
    def invoke(self, messages: list, task_type: str = DEFAULT_TASK_TYPE, **kwargs) -> Any:
        """
        Drop-in replacement for ChatModel.invoke().
        Returns an object with .content attribute (like AIMessage).
        """
        response = self._generate_with_fallback(messages, task_type, stream=False)
        
        # Return a simple object with .content for backward compatibility
        class CompatResponse:
            def __init__(self, content):
                self.content = content
        return CompatResponse(response.content)

    def stream(self, messages: list, task_type: str = DEFAULT_TASK_TYPE, **kwargs) -> Iterator:
        """
        Drop-in replacement for ChatModel.stream().
        Yields objects with .content attribute (like AIMessageChunk).
        """
        yield from self._stream_with_fallback(messages, task_type)

    # ==========================================
    # MODEL SELECTION
    # ==========================================
    def _get_model_id(self, provider_name: str, task_type: str) -> Optional[str]:
        task_models = MODELS.get(task_type, MODELS[DEFAULT_TASK_TYPE])
        return task_models.get(provider_name)

    # ==========================================
    # HEALTH CHECK
    # ==========================================
    def _is_provider_healthy(self, name: str) -> bool:
        health = self._health[name]
        provider = self._providers[name]
        
        if not provider.is_available():
            return False
        
        if health.status == "DISABLED":
            return False
        
        if health.status == "COOLDOWN":
            if health.cooldown_until and datetime.now() > health.cooldown_until:
                health.status = "HEALTHY"
                health.failure_count = 0
                logger.info(f"Provider '{name}' cooldown expired → HEALTHY")
                return True
            return False
        
        return True

    def _mark_failure(self, name: str, error: GatewayError):
        health = self._health[name]
        health.failure_count += 1
        health.last_failure = datetime.now()
        
        if isinstance(error, AuthenticationError):
            health.status = "DISABLED"
            logger.warning(f"Provider '{name}' DISABLED (auth failure)")
        elif health.failure_count >= COOLDOWN_CONFIG["failure_threshold"]:
            health.status = "COOLDOWN"
            health.cooldown_until = datetime.now() + timedelta(
                seconds=COOLDOWN_CONFIG["cooldown_seconds"]
            )
            logger.warning(
                f"Provider '{name}' → COOLDOWN until {health.cooldown_until.strftime('%H:%M:%S')}"
            )

    def _mark_success(self, name: str):
        health = self._health[name]
        health.status = "HEALTHY"
        health.failure_count = 0
        health.last_success = datetime.now()

    # ==========================================
    # USAGE TRACKING
    # ==========================================
    def _record_usage(self, usage: Optional[TokenUsage], success: bool):
        if not usage:
            return
        record = UsageRecord(
            provider=usage.provider,
            model=usage.model,
            task_type=usage.task_type,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            timestamp=datetime.now().isoformat(),
            success=success,
        )
        self._usage_log.append(record)
        if len(self._usage_log) > self._max_usage_records:
            self._usage_log.pop(0)
        
        if usage.input_tokens is not None:
            logger.info(
                f"Tokens [{usage.provider}/{usage.model}] "
                f"in={usage.input_tokens} out={usage.output_tokens} "
                f"total={usage.total_tokens}"
            )

    # ==========================================
    # RETRY LOGIC
    # ==========================================
    def _should_retry(self, error: GatewayError, attempt: int) -> bool:
        if attempt >= RETRY_CONFIG["max_retries"]:
            return False
        if isinstance(error, (AuthenticationError, InvalidRequestError, PermanentProviderError)):
            return False
        return True

    def _get_delay(self, attempt: int) -> float:
        delay = min(
            RETRY_CONFIG["base_delay"] * (2 ** attempt),
            RETRY_CONFIG["max_delay"]
        )
        if RETRY_CONFIG["jitter"]:
            delay += random.uniform(0.1, 0.5)
        return delay

    # ==========================================
    # CORE GENERATION (with fallback chain)
    # ==========================================
    def _get_active_providers(self, task_type: str) -> List[str]:
        """Get ordered list of healthy providers that have a model for this task"""
        active = []
        for name in PROVIDER_PRIORITY:
            if self._is_provider_healthy(name) and self._get_model_id(name, task_type):
                active.append(name)
        return active

    def _generate_with_fallback(self, messages: list, task_type: str, stream: bool = False) -> ProviderResponse:
        active_providers = self._get_active_providers(task_type)
        
        if not active_providers:
            logger.error("No healthy providers available!")
            class EmptyResponse:
                content = "Koi bhi AI provider abhi available nahi hai bhai. Thodi der baad try karein."
            return EmptyResponse()

        last_error = None
        
        for provider_name in active_providers:
            model_id = self._get_model_id(provider_name, task_type)
            provider = self._providers[provider_name]
            
            for attempt in range(RETRY_CONFIG["max_retries"] + 1):
                try:
                    logger.info(f"Request → {provider_name}/{model_id} (task={task_type}, attempt={attempt+1})")
                    response = provider.generate(messages, model_id, task_type=task_type)
                    self._mark_success(provider_name)
                    self._record_usage(response.usage, success=True)
                    logger.info(f"Response ← {provider_name}/{model_id} ✓")
                    return response
                    
                except Exception as raw_error:
                    classified = classify_error(raw_error)
                    last_error = classified
                    logger.warning(f"{provider_name} error: {type(classified).__name__}: {classified}")
                    self._record_usage(None, success=False)
                    
                    if self._should_retry(classified, attempt):
                        delay = self._get_delay(attempt)
                        logger.info(f"Retrying {provider_name} in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        self._mark_failure(provider_name, classified)
                        break
            
            logger.info(f"Falling back from {provider_name}...")

        # All providers failed
        logger.error(f"All providers failed. Last error: {last_error}")
        class FallbackResponse:
            content = "Server par thoda load hai bhai, ek minute baad dobara try karein."
        return FallbackResponse()

    def _stream_with_fallback(self, messages: list, task_type: str) -> Iterator:
        active_providers = self._get_active_providers(task_type)
        
        if not active_providers:
            yield ProviderStreamChunk(content="Koi bhi AI provider abhi available nahi hai bhai.")
            return

        for provider_name in active_providers:
            model_id = self._get_model_id(provider_name, task_type)
            provider = self._providers[provider_name]
            
            try:
                logger.info(f"Stream → {provider_name}/{model_id} (task={task_type})")
                chunk_count = 0
                
                for chunk in provider.stream(messages, model_id, task_type=task_type):
                    chunk_count += 1
                    # Yield LangChain-compatible chunk
                    class CompatChunk:
                        def __init__(self, content):
                            self.content = content
                    yield CompatChunk(chunk.content)
                
                self._mark_success(provider_name)
                logger.info(f"Stream ← {provider_name}/{model_id} ✓ ({chunk_count} chunks)")
                return  # Stream completed successfully
                
            except Exception as raw_error:
                classified = classify_error(raw_error)
                logger.warning(f"{provider_name} stream error: {classified}")
                self._mark_failure(provider_name, classified)
                continue
        
        yield ProviderStreamChunk(content="Server par load hai bhai, dobara try karein.")

    # ==========================================
    # DIAGNOSTICS
    # ==========================================
    def get_health_report(self) -> Dict:
        report = {}
        for name in PROVIDER_PRIORITY:
            h = self._health[name]
            report[name] = {
                "status": h.status,
                "available": self._providers[name].is_available(),
                "failures": h.failure_count,
                "last_success": h.last_success.isoformat() if h.last_success else None,
            }
        return report

    def get_usage_summary(self) -> List[Dict]:
        return [
            {
                "provider": r.provider,
                "model": r.model,
                "task": r.task_type,
                "tokens_in": r.input_tokens,
                "tokens_out": r.output_tokens,
                "success": r.success,
                "time": r.timestamp,
            }
            for r in self._usage_log[-20:]
        ]


# ==========================================
# SINGLETON INSTANCE
# ==========================================
gateway = LLMGateway()