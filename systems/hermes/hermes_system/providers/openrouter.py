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

    def _try_model(self, model: str, messages: list[dict[str, Any]], **kwargs: Any):
        """Call a model and return (response, error_text). Always returns; never raises."""
        try:
            resp = self._call(model, messages, **kwargs)
        except RateLimitError as exc:
            return None, f"rate_limit: {exc}"
        except APIStatusError as exc:
            return None, f"api_status_{exc.status_code}: {str(exc)[:200]}"
        except Exception as exc:  # network errors, malformed responses, etc.
            return None, f"{type(exc).__name__}: {str(exc)[:200]}"

        # OpenRouter occasionally returns 200 with no choices — the body is an
        # error envelope. Detect that and treat it like an error.
        if not getattr(resp, "choices", None):
            err = getattr(resp, "error", None) or getattr(resp, "model_extra", {}).get("error")
            return None, f"no_choices (body error: {err})"
        return resp, None

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Run a chat completion and return the assistant message text.

        Tries primary model first; on any failure (rate-limit, 5xx, or
        no-choices body error) falls back to `settings.model_fallback`. If
        that also fails, raises RuntimeError with both error strings so the
        caller can see what OpenRouter actually said.
        """
        primary = model or self.settings.model_main
        kwargs = {"max_tokens": max_tokens, "temperature": temperature}

        resp, err = self._try_model(primary, messages, **kwargs)
        model_used = primary
        if resp is None:
            resp, err2 = self._try_model(self.settings.model_fallback, messages, **kwargs)
            model_used = self.settings.model_fallback
            if resp is None:
                raise RuntimeError(
                    f"both models failed: primary({primary})={err}; fallback({self.settings.model_fallback})={err2}"
                )

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
