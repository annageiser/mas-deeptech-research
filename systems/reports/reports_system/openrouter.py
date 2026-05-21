"""OpenRouter chat wrapper (same hardened pattern as systems/hermes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import tenacity
from openai import OpenAI
from openai._exceptions import APIStatusError, RateLimitError

from .config import Settings


@dataclass
class TokenTally:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class OpenRouterClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tally = TokenTally()
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.http_referer,
                "X-Title": settings.app_title,
            },
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
        try:
            resp = self._call(model, messages, **kwargs)
        except RateLimitError as exc:
            return None, f"rate_limit: {exc}"
        except APIStatusError as exc:
            return None, f"api_status_{exc.status_code}: {str(exc)[:200]}"
        except Exception as exc:
            return None, f"{type(exc).__name__}: {str(exc)[:200]}"
        if not getattr(resp, "choices", None):
            err = getattr(resp, "error", None) or getattr(resp, "model_extra", {}).get("error")
            return None, f"no_choices (body error: {err})"
        return resp, None

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> str:
        primary = model or self.settings.model_main
        kwargs = {"max_tokens": max_tokens, "temperature": temperature}
        resp, err = self._try_model(primary, messages, **kwargs)
        if resp is None:
            resp, err2 = self._try_model(self.settings.model_fallback, messages, **kwargs)
            if resp is None:
                raise RuntimeError(
                    f"both models failed: primary({primary})={err}; fallback({self.settings.model_fallback})={err2}"
                )
        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.tally.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.tally.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.tally.calls += 1
        return content
