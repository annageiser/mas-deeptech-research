"""OpenRouter chat wrapper (same hardened pattern as systems/hermes)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import tenacity
from openai import OpenAI
from openai._exceptions import APIStatusError, RateLimitError

from .config import Settings


# v0.4.36 / v0.4.38 — reasoning-token strip. Reasoning models (Nemotron 3
# Ultra 550B, Nemotron Super 120B, gpt-oss-120b, Qwen3 reasoning variants)
# emit their chain of thought inside <think>...</think> tags inside the
# visible message content. Until v0.4.36 the reports default was Nemotron
# and the raw content ended up in every daily-report markdown file — the
# "report output not readable" bug.
#
# v0.4.38 hardens the strip: it now matches <think|thinking|reasoning|
# thought|analysis|scratchpad> tag families AND also strips a dangling
# opener with no closer (some providers truncate mid-reasoning when the
# answer hits max_tokens). Server-side suppression via
# extra_body={"reasoning": {"exclude": true}} is the primary defence;
# this regex is the belt-and-braces catch for the residual case.
_REASONING_TAGS = ("think", "thinking", "reasoning", "thought", "analysis", "scratchpad")
_REASONING_BALANCED_RE = re.compile(
    r"<(?:" + "|".join(_REASONING_TAGS) + r")>.*?</(?:" + "|".join(_REASONING_TAGS) + r")>\s*",
    re.DOTALL | re.IGNORECASE,
)
_REASONING_DANGLING_RE = re.compile(
    r"^.*?<(?:" + "|".join(_REASONING_TAGS) + r")>.*?(?=\{|\[|#|\n\n|$)",
    re.DOTALL | re.IGNORECASE,
)


def _strip_reasoning_tags(text: str) -> str:
    """Remove reasoning-tag blocks emitted by reasoning models.

    Two passes:
      1. Balanced <think>...</think> (and siblings) — safe everywhere.
      2. Dangling opener with no closer — only applied when the text
         starts with one. Stops at the first JSON, markdown heading,
         or paragraph break so legitimate prose is never eaten.
    """
    if not text:
        return text
    lower = text.lower()
    if not any(f"<{t}>" in lower for t in _REASONING_TAGS):
        return text
    out = _REASONING_BALANCED_RE.sub("", text).strip()
    # Dangling-opener case — only if the text still leads with a tag.
    if out and any(out.lstrip().lower().startswith(f"<{t}>") for t in _REASONING_TAGS):
        out = _REASONING_DANGLING_RE.sub("", out, count=1).strip()
    return out


# v0.4.38 — body field OpenRouter recognises to drop reasoning tokens
# server-side. Applied on every chat call when settings.reasoning_exclude
# is true (the default).
_REASONING_EXCLUDE_BODY: dict[str, dict[str, bool]] = {"reasoning": {"exclude": True}}


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
        kwargs: dict[str, Any] = {"max_tokens": max_tokens, "temperature": temperature}
        # v0.4.38 — server-side reasoning-token suppression.
        if getattr(self.settings, "reasoning_exclude", True):
            kwargs["extra_body"] = dict(_REASONING_EXCLUDE_BODY)
        resp, err = self._try_model(primary, messages, **kwargs)
        if resp is None:
            resp, err2 = self._try_model(self.settings.model_fallback, messages, **kwargs)
            if resp is None:
                raise RuntimeError(
                    f"both models failed: primary({primary})={err}; fallback({self.settings.model_fallback})={err2}"
                )
        content = resp.choices[0].message.content or ""
        # v0.4.36 — strip reasoning-token wrappers (see _strip_reasoning_tags).
        content = _strip_reasoning_tags(content)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.tally.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.tally.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.tally.calls += 1
        return content
