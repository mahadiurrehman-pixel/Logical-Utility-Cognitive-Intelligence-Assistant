"""
LUCIA Multi-Provider LLM Gateway

Fallback order:

    Groq Primary
        ↓
    Groq MDI
        ↓
    Groq UNI
        ↓
    Hugging Face
        ↓
    Gemini

Features:

- Multiple independent Groq API keys
- Per-provider health
- Per-provider cooldown
- Immediate fallback on rate limits
- Retry transient failures
- Provider/model tracking
- Token tracking
- Streaming fallback
- Detailed terminal diagnostics
- No API keys printed/logged
"""

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional

from llm_config import (
    PROVIDER_PRIORITY,
    MODELS,
    RETRY_CONFIG,
    COOLDOWN_CONFIG,
    DEFAULT_TASK_TYPE,
    FALLBACK_POLICY,
    STREAMING_CONFIG,
)

from providers.base import (
    ProviderResponse,
    ProviderStreamChunk,
    TokenUsage,
)

from providers.groq_provider import GroqProvider
from providers.huggingface_provider import HuggingFaceProvider
from providers.gemini_provider import GeminiProvider


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

logger = logging.getLogger("lucia.llm_gateway")


# ============================================================
# TERMINAL DISPLAY HELPERS
# ============================================================

def _separator():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def _display_name(provider: str) -> str:
    """
    Convert internal provider IDs into readable names.
    """

    names = {
        "groq_primary": "Groq Primary",
        "groq_mdi": "Groq MDI",
        "groq_uni": "Groq UNI",
        "huggingface": "Hugging Face",
        "gemini": "Gemini",
    }

    return names.get(provider, provider)


def _print_request(
    task_type: str,
    provider: str,
    model: str,
):
    """
    Display current provider/model selection.
    """

    print()
    _separator()
    print("🤖 LUCIA LLM REQUEST")
    _separator()
    print(f"🧠 Task     : {task_type}")
    print(f"🔌 Provider : {_display_name(provider)}")
    print(f"🤖 Model    : {model}")
    print("⏳ Status   : Processing...")
    _separator()


def _print_success(
    task_type: str,
    provider: str,
    model: str,
    usage: Optional[TokenUsage] = None,
    elapsed: Optional[float] = None,
):
    """
    Display successful provider response.
    """

    print()
    _separator()
    print("✅ LUCIA RESPONSE")
    _separator()
    print(f"🧠 Task     : {task_type}")
    print(f"🔌 Provider : {_display_name(provider)}")
    print(f"🤖 Model    : {model}")

    if elapsed is not None:
        print(f"⏱️  Time     : {elapsed:.2f}s")

    if usage:

        if usage.input_tokens is not None:
            print(
                f"📥 Input    : "
                f"{usage.input_tokens} tokens"
            )

        if usage.output_tokens is not None:
            print(
                f"📤 Output   : "
                f"{usage.output_tokens} tokens"
            )

        if usage.total_tokens is not None:
            print(
                f"📊 Total    : "
                f"{usage.total_tokens} tokens"
            )

    _separator()
    print()


def _print_rate_limit(
    provider: str,
    model: str,
    error: Exception,
):
    """
    Display rate-limit fallback.
    """

    print()
    print("⚠️  RATE LIMIT DETECTED")
    print(f"🔌 Provider : {_display_name(provider)}")
    print(f"🤖 Model    : {model}")
    print(f"❌ Error    : {error}")
    print("🔄 Action   : Falling back immediately")
    print()


def _print_retry(
    provider: str,
    model: str,
    error: Exception,
    attempt: int,
    max_retries: int,
    delay: float,
):
    """
    Display transient retry information.
    """

    print()
    print("⚠️  PROVIDER ERROR")
    print(f"🔌 Provider : {_display_name(provider)}")
    print(f"🤖 Model    : {model}")
    print(f"❌ Error    : {type(error).__name__}")
    print(f"📝 Details  : {error}")
    print(
        f"🔄 Retry    : "
        f"{attempt + 1}/{max_retries}"
    )
    print(f"⏳ Waiting  : {delay:.2f}s")
    print()


def _print_fallback(
    from_provider: str,
    to_provider: str,
    to_model: str,
):
    """
    Display provider fallback transition.
    """

    print(
        f"➡️  Fallback: "
        f"{_display_name(from_provider)}"
        f" → "
        f"{_display_name(to_provider)}"
    )

    print(f"   🤖 Model: {to_model}")
    print()


def _print_disabled(
    provider: str,
    reason: str,
):
    """
    Display provider disable event.
    """

    print()
    print("🚫 PROVIDER DISABLED")
    print(f"🔌 Provider : {_display_name(provider)}")
    print(f"📝 Reason   : {reason}")
    print()


# ============================================================
# ERRORS
# ============================================================

class GatewayError(Exception):
    pass


class TransientProviderError(GatewayError):
    pass


class RateLimitError(GatewayError):
    pass


class AuthenticationError(GatewayError):
    pass


class InvalidRequestError(GatewayError):
    pass


class ProviderUnavailableError(GatewayError):
    pass


class TimeoutError(GatewayError):
    pass


class PermanentProviderError(GatewayError):
    pass


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

def classify_error(
    error: Exception,
) -> GatewayError:
    """
    Convert arbitrary provider exceptions into
    gateway-level error classes.
    """

    message = str(error).lower()

    # --------------------------------------------------------
    # RATE LIMIT
    # --------------------------------------------------------

    rate_limit_markers = [
        "429",
        "rate limit",
        "rate_limit",
        "rate_limit_exceeded",
        "too many requests",
        "tokens per day",
        "tpd",
        "tokens per minute",
        "tpm",
        "quota exceeded",
        "quota_exceeded",
    ]

    if any(
        marker in message
        for marker in rate_limit_markers
    ):
        return RateLimitError(str(error))

    # --------------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------------

    auth_markers = [
        "401",
        "403",
        "unauthorized",
        "invalid api key",
        "invalid_api_key",
        "authentication",
        "permission denied",
        "forbidden",
    ]

    if any(
        marker in message
        for marker in auth_markers
    ):
        return AuthenticationError(str(error))

    # --------------------------------------------------------
    # TIMEOUT
    # --------------------------------------------------------

    timeout_markers = [
        "timeout",
        "timed out",
        "read timeout",
        "connect timeout",
    ]

    if any(
        marker in message
        for marker in timeout_markers
    ):
        return TimeoutError(str(error))

    # --------------------------------------------------------
    # SERVER / AVAILABILITY
    # --------------------------------------------------------

    unavailable_markers = [
        "500",
        "502",
        "503",
        "504",
        "service unavailable",
        "bad gateway",
        "temporarily unavailable",
        "server error",
    ]

    if any(
        marker in message
        for marker in unavailable_markers
    ):
        return ProviderUnavailableError(str(error))

    # --------------------------------------------------------
    # INVALID REQUEST
    # --------------------------------------------------------

    invalid_markers = [
        "400",
        "invalid request",
        "bad request",
        "invalid argument",
        "invalid parameter",
    ]

    if any(
        marker in message
        for marker in invalid_markers
    ):
        return InvalidRequestError(str(error))

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return TransientProviderError(str(error))


# ============================================================
# PROVIDER HEALTH
# ============================================================

@dataclass
class ProviderHealth:

    status: str = "HEALTHY"

    failure_count: int = 0

    last_failure: Optional[datetime] = None

    cooldown_until: Optional[float] = None

    last_success: Optional[datetime] = None

    last_error_type: Optional[str] = None


# ============================================================
# USAGE RECORD
# ============================================================

@dataclass
class UsageRecord:

    timestamp: datetime

    provider: str

    model: str

    task_type: str

    input_tokens: Optional[int] = None

    output_tokens: Optional[int] = None

    total_tokens: Optional[int] = None


# ============================================================
# GATEWAY
# ============================================================

class LLMGateway:

    def __init__(self):

        # ----------------------------------------------------
        # PROVIDERS
        # ----------------------------------------------------

        self._providers = {

            "groq_primary": GroqProvider(
                "groq_primary"
            ),

            "groq_mdi": GroqProvider(
                "groq_mdi"
            ),

            "groq_uni": GroqProvider(
                "groq_uni"
            ),

            "huggingface": HuggingFaceProvider(),

            "gemini": GeminiProvider(),
        }

        # ----------------------------------------------------
        # HEALTH
        # ----------------------------------------------------

        self._health = {
            name: ProviderHealth()
            for name in self._providers
        }

        # ----------------------------------------------------
        # USAGE
        # ----------------------------------------------------

        self._usage_log = []

        self._max_usage_records = 100

    # ========================================================
    # PUBLIC INVOKE
    # ========================================================

    def invoke(
        self,
        messages: list,
        task_type: str = DEFAULT_TASK_TYPE,
        **kwargs,
    ) -> ProviderResponse:

        return self._generate_with_fallback(
            messages=messages,
            task_type=task_type,
            **kwargs,
        )

    # ========================================================
    # PUBLIC STREAM
    # ========================================================

    def stream(
        self,
        messages: list,
        task_type: str = DEFAULT_TASK_TYPE,
        **kwargs,
    ) -> Iterator[ProviderStreamChunk]:

        yield from self._stream_with_fallback(
            messages=messages,
            task_type=task_type,
            **kwargs,
        )

    # ========================================================
    # MODEL
    # ========================================================

    def _get_model_id(
        self,
        provider_name: str,
        task_type: str,
    ) -> Optional[str]:

        task_models = MODELS.get(
            task_type,
            MODELS.get(
                DEFAULT_TASK_TYPE,
                {},
            ),
        )

        return task_models.get(
            provider_name
        )

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def _is_provider_healthy(
        self,
        provider_name: str,
    ) -> bool:

        provider = self._providers.get(
            provider_name
        )

        if not provider:
            return False

        # ----------------------------------------------------
        # Credential / provider availability
        # ----------------------------------------------------

        try:

            if not provider.is_available():
                return False

        except Exception:

            return False

        # ----------------------------------------------------
        # Health state
        # ----------------------------------------------------

        health = self._health[
            provider_name
        ]

        # ----------------------------------------------------
        # Disabled
        # ----------------------------------------------------

        if health.status == "DISABLED":

            return False

        # ----------------------------------------------------
        # Cooldown
        # ----------------------------------------------------

        if health.cooldown_until:

            if time.time() < health.cooldown_until:

                return False

            # Cooldown expired.
            health.cooldown_until = None
            health.status = "HEALTHY"

        return True

    # ========================================================
    # MARK FAILURE
    # ========================================================

    def _mark_failure(
        self,
        provider_name: str,
        error: GatewayError,
    ):

        health = self._health[
            provider_name
        ]

        health.failure_count += 1

        health.last_failure = datetime.now()

        health.last_error_type = type(
            error
        ).__name__

        # ----------------------------------------------------
        # AUTHENTICATION
        # ----------------------------------------------------

        if isinstance(
            error,
            AuthenticationError,
        ):

            health.status = "DISABLED"

            health.cooldown_until = None

            logger.error(
                "Provider %s disabled due to authentication failure",
                provider_name,
            )

            _print_disabled(
                provider_name,
                "Authentication/API key failure",
            )

            return

        # ----------------------------------------------------
        # RATE LIMIT
        # ----------------------------------------------------

        if isinstance(
            error,
            RateLimitError,
        ):

            health.status = "COOLDOWN"

            health.cooldown_until = (
                time.time()
                + COOLDOWN_CONFIG.get(
                    "rate_limit_cooldown_seconds",
                    300,
                )
            )

            logger.warning(
                "Provider %s rate-limited; cooldown activated",
                provider_name,
            )

            return

        # ----------------------------------------------------
        # NORMAL TRANSIENT FAILURES
        # ----------------------------------------------------

        threshold = COOLDOWN_CONFIG.get(
            "failure_threshold",
            3,
        )

        if health.failure_count >= threshold:

            health.status = "COOLDOWN"

            health.cooldown_until = (
                time.time()
                + COOLDOWN_CONFIG.get(
                    "cooldown_seconds",
                    120,
                )
            )

            logger.warning(
                "Provider %s entered cooldown after %s failures",
                provider_name,
                health.failure_count,
            )

    # ========================================================
    # MARK SUCCESS
    # ========================================================

    def _mark_success(
        self,
        provider_name: str,
    ):

        health = self._health[
            provider_name
        ]

        health.status = "HEALTHY"

        health.failure_count = 0

        health.cooldown_until = None

        health.last_success = datetime.now()

        health.last_error_type = None

    # ========================================================
    # USAGE
    # ========================================================

    def _record_usage(
        self,
        usage: Optional[TokenUsage],
    ):

        if not usage:
            return

        record = UsageRecord(

            timestamp=datetime.now(),

            provider=usage.provider,

            model=usage.model,

            task_type=usage.task_type,

            input_tokens=usage.input_tokens,

            output_tokens=usage.output_tokens,

            total_tokens=usage.total_tokens,
        )

        self._usage_log.append(record)

        if len(
            self._usage_log
        ) > self._max_usage_records:

            self._usage_log = (
                self._usage_log[
                    -self._max_usage_records:
                ]
            )

    # ========================================================
    # RETRY DECISION
    # ========================================================

    def _should_retry(
        self,
        error: GatewayError,
        attempt: int,
    ) -> bool:

        max_retries = RETRY_CONFIG.get(
            "max_retries",
            2,
        )

        if attempt >= max_retries:
            return False

        # ----------------------------------------------------
        # NEVER retry these
        # ----------------------------------------------------

        if isinstance(
            error,
            (
                RateLimitError,
                AuthenticationError,
                InvalidRequestError,
                PermanentProviderError,
            ),
        ):

            return False

        return (
            FALLBACK_POLICY.get(
                "retry_transient_errors",
                True,
            )
        )

    # ========================================================
    # RETRY DELAY
    # ========================================================

    def _get_delay(
        self,
        attempt: int,
    ) -> float:

        base_delay = RETRY_CONFIG.get(
            "base_delay",
            1.0,
        )

        max_delay = RETRY_CONFIG.get(
            "max_delay",
            8.0,
        )

        delay = min(
            base_delay * (
                2 ** attempt
            ),
            max_delay,
        )

        if RETRY_CONFIG.get(
            "jitter",
            True,
        ):

            delay += random.uniform(
                0.1,
                0.5,
            )

        return delay

    # ========================================================
    # ACTIVE PROVIDERS
    # ========================================================

    def _get_active_providers(
        self,
        task_type: str,
    ) -> list[tuple[str, str]]:

        active = []

        for provider_name in PROVIDER_PRIORITY:

            if not self._is_provider_healthy(
                provider_name
            ):
                continue

            model_id = self._get_model_id(
                provider_name,
                task_type,
            )

            if not model_id:
                continue

            active.append(
                (
                    provider_name,
                    model_id,
                )
            )

        return active

    # ========================================================
    # GENERATION FALLBACK
    # ========================================================

    def _generate_with_fallback(
        self,
        messages: list,
        task_type: str,
        **kwargs,
    ) -> ProviderResponse:

        active_providers = (
            self._get_active_providers(
                task_type
            )
        )

        if not active_providers:

            raise GatewayError(
                "No LLM providers are currently available."
            )

        max_provider_attempts = (
            FALLBACK_POLICY.get(
                "max_provider_attempts",
                len(active_providers),
            )
        )

        active_providers = (
            active_providers[
                :max_provider_attempts
            ]
        )

        last_error = None

        # ----------------------------------------------------
        # REQUEST START
        # ----------------------------------------------------

        print()
        print("╔════════════════════════════════════════╗")
        print("║       🧠 LUCIA MODEL ROUTER            ║")
        print("╚════════════════════════════════════════╝")

        print(
            f"📋 Task: {task_type}"
        )

        print(
            f"🔗 Provider chain: "
            f"{' → '.join(_display_name(p) for p, _ in active_providers)}"
        )

        print()

        # ----------------------------------------------------
        # PROVIDER FALLBACK LOOP
        # ----------------------------------------------------

        for index, (
            provider_name,
            model_id,
        ) in enumerate(active_providers):

            provider = self._providers[
                provider_name
            ]

            # ------------------------------------------------
            # DISPLAY PROVIDER
            # ------------------------------------------------

            _print_request(
                task_type=task_type,
                provider=provider_name,
                model=model_id,
            )

            logger.info(
                "Trying LLM provider=%s model=%s",
                provider_name,
                model_id,
            )

            attempt = 0

            # Track start time.
            provider_start = time.perf_counter()

            # ------------------------------------------------
            # RETRY SAME PROVIDER
            # ------------------------------------------------

            while True:

                try:

                    response = provider.generate(
                        messages,
                        model_id,
                        task_type=task_type,
                        **kwargs,
                    )

                    elapsed = (
                        time.perf_counter()
                        - provider_start
                    )

                    self._mark_success(
                        provider_name
                    )

                    self._record_usage(
                        response.usage
                    )

                    _print_success(
                        task_type=task_type,
                        provider=provider_name,
                        model=model_id,
                        usage=response.usage,
                        elapsed=elapsed,
                    )

                    return response

                except Exception as raw_error:

                    error = classify_error(
                        raw_error
                    )

                    last_error = error

                    logger.warning(
                        "Provider %s failed: %s: %s",
                        provider_name,
                        type(error).__name__,
                        error,
                    )

                    # ----------------------------------------
                    # RATE LIMIT
                    #
                    # DO NOT RETRY.
                    # Immediately move to next provider.
                    # ----------------------------------------

                    if isinstance(
                        error,
                        RateLimitError,
                    ):

                        self._mark_failure(
                            provider_name,
                            error,
                        )

                        _print_rate_limit(
                            provider=provider_name,
                            model=model_id,
                            error=error,
                        )

                        break

                    # ----------------------------------------
                    # PERMANENT / AUTH
                    # ----------------------------------------

                    if isinstance(
                        error,
                        (
                            AuthenticationError,
                            InvalidRequestError,
                            PermanentProviderError,
                        ),
                    ):

                        self._mark_failure(
                            provider_name,
                            error,
                        )

                        print()
                        print("❌ PROVIDER FAILED")
                        print(
                            f"🔌 Provider : "
                            f"{_display_name(provider_name)}"
                        )
                        print(
                            f"🤖 Model    : {model_id}"
                        )
                        print(
                            f"❌ Error    : "
                            f"{type(error).__name__}"
                        )
                        print(
                            f"📝 Details  : {error}"
                        )
                        print()

                        break

                    # ----------------------------------------
                    # TRANSIENT RETRY
                    # ----------------------------------------

                    if self._should_retry(
                        error,
                        attempt,
                    ):

                        delay = self._get_delay(
                            attempt
                        )

                        _print_retry(
                            provider=provider_name,
                            model=model_id,
                            error=error,
                            attempt=attempt,
                            max_retries=RETRY_CONFIG.get(
                                "max_retries",
                                2,
                            ),
                            delay=delay,
                        )

                        time.sleep(delay)

                        attempt += 1

                        continue

                    # ----------------------------------------
                    # RETRIES EXHAUSTED
                    # ----------------------------------------

                    self._mark_failure(
                        provider_name,
                        error,
                    )

                    print()
                    print("❌ PROVIDER FAILED")
                    print(
                        f"🔌 Provider : "
                        f"{_display_name(provider_name)}"
                    )
                    print(
                        f"🤖 Model    : {model_id}"
                    )
                    print(
                        f"❌ Error    : "
                        f"{type(error).__name__}"
                    )
                    print(
                        f"📝 Details  : {error}"
                    )
                    print(
                        "➡️  Moving to next provider..."
                    )
                    print()

                    break

            # ------------------------------------------------
            # FALLBACK TO NEXT PROVIDER
            # ------------------------------------------------

            if index + 1 < len(
                active_providers
            ):

                next_provider, next_model = (
                    active_providers[index + 1]
                )

                _print_fallback(
                    from_provider=provider_name,
                    to_provider=next_provider,
                    to_model=next_model,
                )

        # ====================================================
        # ALL PROVIDERS FAILED
        # ====================================================

        print()
        print("╔════════════════════════════════════════╗")
        print("║       ❌ LUCIA ALL PROVIDERS FAILED    ║")
        print("╚════════════════════════════════════════╝")

        error_message = (
            str(last_error)
            if last_error
            else "Unknown provider failure"
        )

        print(
            f"📝 Last error: {error_message}"
        )

        print()

        raise GatewayError(
            "All configured LLM providers failed. "
            f"Last error: {error_message}"
        )

    # ========================================================
    # STREAMING FALLBACK
    # ========================================================

    def _stream_with_fallback(
        self,
        messages: list,
        task_type: str,
        **kwargs,
    ) -> Iterator[ProviderStreamChunk]:

        active_providers = (
            self._get_active_providers(
                task_type
            )
        )

        if not active_providers:

            raise GatewayError(
                "No LLM providers are currently available."
            )

        print()
        print("╔════════════════════════════════════════╗")
        print("║       ⚡ LUCIA STREAMING ROUTER        ║")
        print("╚════════════════════════════════════════╝")

        print(
            f"📋 Task: {task_type}"
        )

        print(
            f"🔗 Chain: "
            f"{' → '.join(_display_name(p) for p, _ in active_providers)}"
        )

        print()

        # ----------------------------------------------------
        # Each provider gets a fresh output_started state.
        # ----------------------------------------------------

        for index, (
            provider_name,
            model_id,
        ) in enumerate(active_providers):

            provider = self._providers[
                provider_name
            ]

            output_started = False

            _print_request(
                task_type=task_type,
                provider=provider_name,
                model=model_id,
            )

            try:

                stream_start = time.perf_counter()

                for chunk in provider.stream(
                    messages,
                    model_id,
                    task_type=task_type,
                    **kwargs,
                ):

                    if chunk.content:

                        output_started = True

                        yield chunk

                elapsed = (
                    time.perf_counter()
                    - stream_start
                )

                self._mark_success(
                    provider_name
                )

                print()
                _separator()
                print("✅ STREAM COMPLETE")
                _separator()
                print(
                    f"🔌 Provider : "
                    f"{_display_name(provider_name)}"
                )
                print(
                    f"🤖 Model    : {model_id}"
                )
                print(
                    f"⏱️  Time     : {elapsed:.2f}s"
                )
                _separator()
                print()

                return

            except Exception as raw_error:

                error = classify_error(
                    raw_error
                )

                self._mark_failure(
                    provider_name,
                    error,
                )

                # --------------------------------------------
                # Display error
                # --------------------------------------------

                print()
                print("❌ STREAMING PROVIDER FAILED")
                print(
                    f"🔌 Provider : "
                    f"{_display_name(provider_name)}"
                )
                print(
                    f"🤖 Model    : {model_id}"
                )
                print(
                    f"❌ Error    : "
                    f"{type(error).__name__}"
                )
                print(
                    f"📝 Details  : {error}"
                )
                print()

                # --------------------------------------------
                # If output already started, don't switch.
                # --------------------------------------------

                if output_started:

                    raise GatewayError(
                        "Streaming failed after output "
                        f"started from provider "
                        f"{provider_name}: {error}"
                    )

                # --------------------------------------------
                # Pre-output fallback
                # --------------------------------------------

                if not STREAMING_CONFIG.get(
                    "allow_pre_output_fallback",
                    True,
                ):

                    raise GatewayError(
                        f"Streaming failed: {error}"
                    )

                if index + 1 < len(
                    active_providers
                ):

                    next_provider, next_model = (
                        active_providers[index + 1]
                    )

                    _print_fallback(
                        from_provider=provider_name,
                        to_provider=next_provider,
                        to_model=next_model,
                    )

                    continue

        # ====================================================
        # ALL STREAMING PROVIDERS FAILED
        # ====================================================

        raise GatewayError(
            "All streaming providers failed."
        )

    # ========================================================
    # HEALTH REPORT
    # ========================================================

    def get_health_report(self) -> dict:

        report = {}

        for provider_name, health in (
            self._health.items()
        ):

            report[provider_name] = {

                "status": health.status,

                "failure_count": (
                    health.failure_count
                ),

                "last_failure": (
                    health.last_failure.isoformat()
                    if health.last_failure
                    else None
                ),

                "cooldown_until": (
                    health.cooldown_until
                ),

                "last_success": (
                    health.last_success.isoformat()
                    if health.last_success
                    else None
                ),

                "last_error_type": (
                    health.last_error_type
                ),
            }

        return report

    # ========================================================
    # USAGE REPORT
    # ========================================================

    def get_usage_report(
        self,
    ) -> list[dict]:

        return [

            {
                "timestamp": (
                    record.timestamp.isoformat()
                ),

                "provider": record.provider,

                "model": record.model,

                "task_type": record.task_type,

                "input_tokens": (
                    record.input_tokens
                ),

                "output_tokens": (
                    record.output_tokens
                ),

                "total_tokens": (
                    record.total_tokens
                ),
            }

            for record in self._usage_log
        ]


# ============================================================
# SINGLETON
# ============================================================

gateway = LLMGateway()