"""LLM model factory.

MASFactory ships two OpenAI adapters:
- `OpenAIModel`   — uses the Responses API, which OpenRouter does NOT support.
- `LegacyOpenAIModel` — uses Chat Completions, which OpenRouter DOES support.

We always use `LegacyOpenAIModel` and pass `base_url=https://openrouter.ai/api/v1`.
"""

from __future__ import annotations

from masfactory import LegacyOpenAIModel

from .config import Settings


def _openrouter_kwargs(settings: Settings) -> dict:
    """OpenRouter recommends sending HTTP-Referer and X-Title for analytics."""
    return {
        "default_headers": {
            "HTTP-Referer": settings.http_referer,
            "X-Title": settings.app_title,
        }
    }


def build_main_model(settings: Settings) -> LegacyOpenAIModel:
    return LegacyOpenAIModel(
        model_name=settings.model_main,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        **_openrouter_kwargs(settings),
    )


def build_fallback_model(settings: Settings) -> LegacyOpenAIModel:
    return LegacyOpenAIModel(
        model_name=settings.model_fallback,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        **_openrouter_kwargs(settings),
    )
