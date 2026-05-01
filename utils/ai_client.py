"""
utils/ai_client.py
──────────────────
Centralized AI provider abstraction layer.

Provides a unified interface to multiple LLM providers (OpenAI, Gemini, etc.)
by leveraging the OpenAI Python SDK's support for custom base URLs.

USAGE:
    from utils.ai_client import get_ai_client, get_model_name

    client = get_ai_client()                    # uses AI_PROVIDER env var
    model  = get_model_name(tier="fast")        # returns provider-appropriate model

    response = client.chat.completions.create(
        model=model,
        messages=[...],
    )

ADDING A NEW PROVIDER:
    1. Add a new entry to PROVIDER_REGISTRY below.
    2. Add the corresponding API key to .env
    3. Set AI_PROVIDER=<your_provider> in .env
    That's it — all consumer code automatically uses the new provider.
"""

import os
import logging
from functools import lru_cache
from typing import Optional
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  PROVIDER REGISTRY
# ──────────────────────────────────────────────────────────────────────
#  Each provider entry contains:
#    - api_key_env  : name of the .env variable holding the API key
#    - base_url     : API endpoint (None = default OpenAI endpoint)
#    - models       : mapping of tier names → model identifiers
#
#  Supported tiers:
#    "default"  — highest quality, used for complex generation tasks
#    "fast"     — cheaper / faster, used for interviews & evaluations
#
#  To add a new provider, just add a new key here.
#  To remove one, delete the key. No other files need to change.
# ══════════════════════════════════════════════════════════════════════

PROVIDER_REGISTRY: dict[str, dict] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,  # default OpenAI endpoint
        "models": {
            "default": "gpt-4o",
            "fast": "gpt-4o-mini",
        },
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": {
            "default": "gemini-2.5-flash",
            "fast": "gemini-2.5-flash",
        },
    },
    # ── Add new providers below ──────────────────────────────────────
    # "anthropic": {
    #     "api_key_env": "ANTHROPIC_API_KEY",
    #     "base_url": "https://...",
    #     "models": {
    #         "default": "claude-sonnet-4-20250514",
    #         "fast": "claude-haiku-...",
    #     },
    # },
}

# Default provider when AI_PROVIDER is not set in .env
_DEFAULT_PROVIDER = "openai"


# ══════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════

def _resolve_provider(provider: Optional[str] = None) -> str:
    """Resolve the provider name from the argument or environment variable."""
    name = (provider or os.getenv("AI_PROVIDER", _DEFAULT_PROVIDER)).lower().strip()
    if name not in PROVIDER_REGISTRY:
        available = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown AI provider '{name}'. "
            f"Available providers: {available}. "
            f"Register new providers in utils/ai_client.py → PROVIDER_REGISTRY."
        )
    return name


def get_ai_client(provider: Optional[str] = None) -> OpenAI:
    """
    Return an OpenAI-compatible client configured for the given provider.

    Args:
        provider: Provider name (e.g. "openai", "gemini").
                  Defaults to the AI_PROVIDER environment variable,
                  which itself defaults to "openai".

    Returns:
        An OpenAI client instance configured with the correct
        API key and base URL for the chosen provider.

    Example:
        client = get_ai_client()           # use env default
        client = get_ai_client("gemini")   # force Gemini
    """
    name = _resolve_provider(provider)
    config = PROVIDER_REGISTRY[name]

    api_key = os.getenv(config["api_key_env"], "")
    if not api_key:
        logger.warning(
            "API key for provider '%s' is not set (env var: %s). "
            "Requests will likely fail.",
            name, config["api_key_env"],
        )

    kwargs = {"api_key": api_key}
    if config["base_url"]:
        kwargs["base_url"] = config["base_url"]

    logger.info("Creating AI client for provider '%s'", name)
    return OpenAI(**kwargs)


def get_async_ai_client(provider: str | None = None) -> AsyncOpenAI:
    """
    Return an AsyncOpenAI-compatible client configured for the given provider.
    """
    name = _resolve_provider(provider)
    config = PROVIDER_REGISTRY[name]

    api_key = os.getenv(config["api_key_env"], "")
    if not api_key:
        logger.warning(
            "API key for provider '%s' is not set (env var: %s).",
            name, config["api_key_env"],
        )

    kwargs = {"api_key": api_key}
    if config["base_url"]:
        kwargs["base_url"] = config["base_url"]

    logger.info("Creating Async AI client for provider '%s'", name)
    return AsyncOpenAI(**kwargs)


def get_model_name(tier: str = "default", provider: str | None = None) -> str:
    """
    Return the model identifier for the given quality tier and provider.

    Args:
        tier:     Quality tier — "default" (best) or "fast" (cheaper).
        provider: Provider name override. Defaults to AI_PROVIDER env var.

    Returns:
        Model identifier string (e.g. "gpt-4o", "gemini-2.0-flash").

    Example:
        model = get_model_name()                   # → "gpt-4o" (if openai)
        model = get_model_name("fast")             # → "gpt-4o-mini"
        model = get_model_name("fast", "gemini")   # → "gemini-2.0-flash-lite"
    """
    name = _resolve_provider(provider)
    models = PROVIDER_REGISTRY[name]["models"]

    if tier not in models:
        available = ", ".join(sorted(models.keys()))
        raise ValueError(
            f"Unknown model tier '{tier}' for provider '{name}'. "
            f"Available tiers: {available}."
        )

    return models[tier]


def get_current_provider() -> str:
    """Return the currently active provider name (resolved from env)."""
    return _resolve_provider()
