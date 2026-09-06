"""
LUCIA LLM Configuration & Model Registry

Centralized configuration for:
- Provider credentials
- Provider priority
- Model routing
- Retry policies
- Cooldown policies
- Streaming
- Token tracking

Provider strategy:

1. Hugging Face  -> Primary
2. Groq          -> First fallback
3. Gemini        -> Final fallback

IMPORTANT:
- This file contains configuration only.
- Provider API calls belong in provider adapters.
- API keys must never be hardcoded.
- Free availability and rate limits are controlled by each provider.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(
    dotenv_path=ENV_PATH,
    override=True,
)


def _clean(key: str) -> str:
    """
    Read and normalize an environment variable.
    """
    return (
        (os.getenv(key, "") or "")
        .strip()
        .strip('"')
        .strip("'")
    )


# ============================================================
# CREDENTIALS
# ============================================================

CREDENTIALS = {
    "groq": _clean("GROQ_API_KEY"),

    "huggingface": _clean("HF_TOKEN"),

    "gemini": (
        _clean("GEMINI_API_KEY")
        or _clean("GOOGLE_API_KEY")
    ),

    
}


# Google SDK compatibility
if CREDENTIALS["gemini"]:
    os.environ["GOOGLE_API_KEY"] = CREDENTIALS["gemini"]


# ============================================================
# PROVIDER SETTINGS
# ============================================================

PROVIDERS = {

    "groq": {
            "enabled": bool(CREDENTIALS["groq"]),
            "free_first": False,
        },

    "huggingface": {
        "enabled": bool(CREDENTIALS["huggingface"]),
        "free_first": True,
    },

    

    "gemini": {
        "enabled": bool(CREDENTIALS["gemini"]),
        "free_first": True,
    },
}


# ============================================================
# PROVIDER PRIORITY
#
# Order = fallback order.
#
# 1. Hugging Face
# 2. Groq
# 3. Gemini
# ============================================================

PROVIDER_PRIORITY = [
    "groq",
    "huggingface",
    "gemini",
]


# ============================================================
# MODEL REGISTRY
#
# task → provider → model
#
# Provider order follows PROVIDER_PRIORITY:
#
# Hugging Face → Groq → Gemini
# ============================================================

MODELS = {

    # --------------------------------------------------------
    # GENERAL CHAT
    # --------------------------------------------------------

    "chat": {

        "groq": "openai/gpt-oss-120b",
        # Primary
        "huggingface": "Qwen/Qwen3.5-9B",

        # First fallback
        

        # Final fallback
        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # CODING
    # --------------------------------------------------------

    "coding": {

        "groq": "openai/gpt-oss-120b",

        # Primary coding model
        "huggingface": "Qwen/Qwen3-Coder-Next",

        # First fallback
        

        # Final fallback
        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # REASONING
    # --------------------------------------------------------

    "reasoning": {

        "groq": "openai/gpt-oss-120b",

        # Primary reasoning model
        "huggingface": "deepseek-ai/DeepSeek-R1",

        # First fallback
        

        # Final fallback
        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    "summary": {

        "groq": "openai/gpt-oss-20b",

        # Primary
        "huggingface": "Qwen/Qwen3.5-9B",

        # First fallback
        

        # Final fallback
        "gemini": "gemini-3.5-flash-lite",
    },
}


# ============================================================
# DEFAULT TASK
# ============================================================

DEFAULT_TASK_TYPE = "chat"


# ============================================================
# RETRY CONFIGURATION
# ============================================================

RETRY_CONFIG = {

    # Maximum retries for a single provider.
    "max_retries": 2,

    # Initial retry delay.
    "base_delay": 1.0,

    # Maximum retry delay.
    "max_delay": 8.0,

    # Random jitter prevents synchronized retries.
    "jitter": True,
}


# ============================================================
# COOLDOWN CONFIGURATION
# ============================================================

COOLDOWN_CONFIG = {

    # Consecutive failures before cooldown.
    "failure_threshold": 3,

    # Provider cooldown duration.
    "cooldown_seconds": 120,

    # Recovery check interval.
    "recovery_check_seconds": 60,
}


# ============================================================
# FALLBACK POLICY
# ============================================================

FALLBACK_POLICY = {

    # Enable provider fallback.
    "enabled": True,

    # Retry temporary errors.
    "retry_transient_errors": True,

    # Maximum number of providers attempted.
    "max_provider_attempts": len(PROVIDER_PRIORITY),

    # Never retry permanent request errors indefinitely.
    "retry_permanent_errors": False,
}


# ============================================================
# STREAMING
# ============================================================

STREAMING_CONFIG = {

    "enabled": True,

    # If streaming fails before output begins,
    # Gateway may attempt another provider.
    "allow_pre_output_fallback": True,
}


# ============================================================
# TOKEN TRACKING
# ============================================================

TOKEN_TRACKING = {

    "enabled": True,

    # Never invent token counts.
    "allow_estimated_usage": False,

    # Track usage separately by task.
    "track_task_type": True,

    # Track provider/model.
    "track_provider": True,

    "track_model": True,
}


# ============================================================
# LOGGING
# ============================================================

LOGGING_CONFIG = {

    "enabled": True,

    # NEVER log credentials.
    "log_credentials": False,

    # Do not log complete user prompts by default.
    "log_full_prompts": False,

    # Log provider/model decisions.
    "log_provider_selection": True,

    # Log fallback events.
    "log_fallback": True,

    # Log retry events.
    "log_retries": True,
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_model(
    task_type: str,
    provider: str,
) -> str | None:
    """
    Return the configured model for a task/provider pair.
    """

    task_models = MODELS.get(task_type)

    if task_models is None:
        task_models = MODELS.get(
            DEFAULT_TASK_TYPE,
            {},
        )

    return task_models.get(provider)


def is_provider_enabled(
    provider: str,
) -> bool:
    """
    Check whether a provider is enabled.
    """

    config = PROVIDERS.get(provider)

    if not config:
        return False

    return bool(
        config.get("enabled", False)
    )


def get_enabled_providers() -> list[str]:
    """
    Return enabled providers in priority order.

    Order:
        Hugging Face → Groq → Gemini
    """

    return [
        provider
        for provider in PROVIDER_PRIORITY
        if is_provider_enabled(provider)
    ]


def get_provider_chain(
    task_type: str,
) -> list[dict]:
    """
    Return the provider/model fallback chain.

    Example:

        [   
            {
                "provider": "groq",
                "model": "...",
           },
            {
                "provider": "huggingface",
                "model": "...",
            },
            {
                "provider": "gemini",
                "model": "...",
            },
        ]
    """

    chain = []

    for provider in get_enabled_providers():

        model = get_model(
            task_type=task_type,
            provider=provider,
        )

        if not model:
            continue

        chain.append(
            {
                "provider": provider,
                "model": model,
            }
        )

    return chain


def get_primary_provider(
    task_type: str = DEFAULT_TASK_TYPE,
) -> str | None:
    """
    Return the first enabled provider for a task.

    Expected primary:
        Hugging Face
    """

    chain = get_provider_chain(task_type)

    if not chain:
        return None

    return chain[0]["provider"]


def get_primary_model(
    task_type: str = DEFAULT_TASK_TYPE,
) -> str | None:
    """
    Return the primary model for a task.
    """

    chain = get_provider_chain(task_type)

    if not chain:
        return None

    return chain[0]["model"]


def validate_configuration() -> dict:
    """
    Validate provider/model configuration.

    Returns a diagnostic dictionary.
    """

    result = {
        "providers": {},
        "tasks": {},
        "valid": True,
    }

    # --------------------------------------------------------
    # Provider validation
    # --------------------------------------------------------

    for provider in PROVIDER_PRIORITY:

        enabled = is_provider_enabled(provider)

        result["providers"][provider] = {
            "enabled": enabled,
            "has_credential": bool(
                CREDENTIALS.get(provider)
            ),
        }

    # --------------------------------------------------------
    # Task validation
    # --------------------------------------------------------

    for task_type, provider_models in MODELS.items():

        result["tasks"][task_type] = {}

        for provider in PROVIDER_PRIORITY:

            model = provider_models.get(provider)

            result["tasks"][task_type][provider] = {
                "configured": bool(model),
                "enabled": is_provider_enabled(provider),
                "model": model,
            }

    # --------------------------------------------------------
    # At least one provider should be available.
    # --------------------------------------------------------

    if not get_enabled_providers():
        result["valid"] = False

    return result

