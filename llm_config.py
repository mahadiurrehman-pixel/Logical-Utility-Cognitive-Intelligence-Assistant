
"""
LUCIA LLM Configuration & Model Registry

Provider fallback strategy:

1. Groq Primary
2. Groq MDI
3. Groq UNI
4. Hugging Face
5. Gemini

API keys are loaded ONLY from environment variables.
Never hardcode credentials in this file.
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
    # --------------------------------------------------------
    # GROQ
    # --------------------------------------------------------

    "groq_primary": _clean("GROQ_API_KEY"),

    "groq_mdi": _clean("GROQ_API_KEY_MDI"),

    "groq_uni": _clean("GROQ_API_KEY_UNI"),

    # --------------------------------------------------------
    # OTHER PROVIDERS
    # --------------------------------------------------------

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

    "groq_primary": {
        "enabled": bool(CREDENTIALS["groq_primary"]),
        "type": "groq",
        "label": "Groq Primary",
    },

    "groq_mdi": {
        "enabled": bool(CREDENTIALS["groq_mdi"]),
        "type": "groq",
        "label": "Groq MDI",
    },

    "groq_uni": {
        "enabled": bool(CREDENTIALS["groq_uni"]),
        "type": "groq",
        "label": "Groq UNI",
    },

    "huggingface": {
        "enabled": bool(CREDENTIALS["huggingface"]),
        "type": "huggingface",
        "label": "Hugging Face",
    },

    "gemini": {
        "enabled": bool(CREDENTIALS["gemini"]),
        "type": "gemini",
        "label": "Gemini",
    },
}


# ============================================================
# PROVIDER PRIORITY
#
# IMPORTANT:
# This is the actual fallback order.
# ============================================================

PROVIDER_PRIORITY = [
    "groq_primary",
    "groq_mdi",
    "groq_uni",
    "huggingface",
    "gemini",
]


# ============================================================
# MODEL REGISTRY
#
# task_type -> logical provider -> model
#
# All three Groq accounts can use the same model.
# ============================================================

MODELS = {

    # --------------------------------------------------------
    # GENERAL CHAT
    # --------------------------------------------------------

    "chat": {

        "groq_primary": "openai/gpt-oss-120b",
        "groq_mdi": "openai/gpt-oss-120b",
        "groq_uni": "openai/gpt-oss-120b",

        "huggingface": "Qwen/Qwen3.5-9B",

        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # CODING
    # --------------------------------------------------------

    "coding": {

        "groq_primary": "openai/gpt-oss-120b",
        "groq_mdi": "openai/gpt-oss-120b",
        "groq_uni": "openai/gpt-oss-120b",

        "huggingface": "Qwen/Qwen3-Coder-Next",

        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # REASONING
    # --------------------------------------------------------

    "reasoning": {

        "groq_primary": "openai/gpt-oss-120b",
        "groq_mdi": "openai/gpt-oss-120b",
        "groq_uni": "openai/gpt-oss-120b",

        "huggingface": "deepseek-ai/DeepSeek-R1",

        "gemini": "gemini-3.8-flash",
    },


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    "summary": {

        "groq_primary": "openai/gpt-oss-20b",
        "groq_mdi": "openai/gpt-oss-20b",
        "groq_uni": "openai/gpt-oss-20b",

        "huggingface": "Qwen/Qwen3.5-9B",

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

    # Maximum retries for transient errors
    # on the SAME provider.
    "max_retries": 2,

    "base_delay": 1.0,

    "max_delay": 8.0,

    "jitter": True,
}


# ============================================================
# COOLDOWN CONFIGURATION
# ============================================================

COOLDOWN_CONFIG = {

    # Consecutive failures before normal cooldown.
    "failure_threshold": 3,

    # Normal provider cooldown.
    "cooldown_seconds": 120,

    # Rate-limit cooldown.
    #
    # The provider will be skipped during this period.
    "rate_limit_cooldown_seconds": 300,

    "recovery_check_seconds": 60,
}


# ============================================================
# FALLBACK POLICY
# ============================================================

FALLBACK_POLICY = {

    "enabled": True,

    "retry_transient_errors": True,

    "max_provider_attempts": len(PROVIDER_PRIORITY),

    "retry_permanent_errors": False,

    # IMPORTANT:
    # Rate-limit errors immediately move to
    # the next provider/key instead of retrying.
    "rate_limit_immediate_fallback": True,
}


# ============================================================
# STREAMING
# ============================================================

STREAMING_CONFIG = {

    "enabled": True,

    # If a provider fails before producing output,
    # gateway can use another provider.
    "allow_pre_output_fallback": True,
}


# ============================================================
# TOKEN TRACKING
# ============================================================

TOKEN_TRACKING = {

    "enabled": True,

    "allow_estimated_usage": False,

    "track_task_type": True,

    "track_provider": True,

    "track_model": True,
}


# ============================================================
# LOGGING
# ============================================================

LOGGING_CONFIG = {

    "enabled": True,

    "log_credentials": False,

    "log_full_prompts": False,

    "log_provider_selection": True,

    "log_fallback": True,

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
    Return configured model for task/provider.
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
    Check whether provider is enabled.
    """

    config = PROVIDERS.get(provider)

    if not config:
        return False

    return bool(
        config.get("enabled", False)
    )


def get_enabled_providers() -> list[str]:
    """
    Return enabled providers in actual fallback order.
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
    Build complete provider/model fallback chain.
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
    Return first enabled provider.
    """

    chain = get_provider_chain(task_type)

    if not chain:
        return None

    return chain[0]["provider"]


def get_primary_model(
    task_type: str = DEFAULT_TASK_TYPE,
) -> str | None:
    """
    Return model of first enabled provider.
    """

    chain = get_provider_chain(task_type)

    if not chain:
        return None

    return chain[0]["model"]


def validate_configuration() -> dict:
    """
    Validate provider/model configuration.
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
            "type": PROVIDERS.get(
                provider,
                {},
            ).get("type"),
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
    # At least one provider
    # --------------------------------------------------------

    if not get_enabled_providers():
        result["valid"] = False

    return result

