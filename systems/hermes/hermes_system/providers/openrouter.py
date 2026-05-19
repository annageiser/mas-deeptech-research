"""OpenRouter provider — direct OpenAI SDK against the OpenRouter base_url.

Why not use the hermes-agent CLI: it's designed as an interactive personal-
assistant agent with messaging gateways (Telegram/Discord/...). For a
cron-driven batch task the agent's interactive flow is the wrong shape. We
take the Hermes *pattern* (single AIAgent loop + skills + memory) but call
the model ourselves so the system can run headless on a VPS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import tenacity
from openai import OpenAI
from openai._exceptions import APIStatusError, RateLimitError

from ..config import Settings


@dataclass
class TokenTally:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    per_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        slot = self.per_model.setdefault(model, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
        slot["input_tokens"] += input_tokens
        slot["output_tokens"] += output_tokens
        slot["calls"] += 1


class OpenRouterProvider:
    """Thin wrapper around `openai.OpenAI` configured for OpenRouter.

    Supports a primary + fallback model: a `RateLimitError` or 5xx on the
    primary triggers one retry against the fallback, then the call surfaces
    the exception.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.tally = TokenTally()
        default_headers = {
            "HTTP-Referer": settings.http_referer,
            "X-Title": settings.app_title,
        }
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers=default_headers,
        )

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=20),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type((RateLimitError,)),
        reraise=True,
    )
    def _call(self, model: str, messages: list[dict[str, Any]], **kwargs: Any):
        return self._client.chat.completions.create(model=model, messages=messages, **kwargs)

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Run a chat completion and return the assistant message text."""
        primary = model or self.settings.model_main
        try:
            resp = self._call(primary, messages, max_tokens=max_tokens, temperature=temperature)
            model_used = primary
        except (RateLimitError, APIStatusError) as exc:
            if isinstance(exc, APIStatusError) and exc.status_code < 500:
                raise
            resp = self._call(
                self.settings.model_fallback, messages, max_tokens=max_tokens, temperature=temperature
            )
            model_used = self.settings.model_fallback

        choice = resp.choices[0]
        content = choice.message.content or ""

        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.tally.record(
                model=model_used,
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )
        return content
