"""LLM model factory.

MASFactory ships two OpenAI adapters:
- `OpenAIModel`   — uses the Responses API, which OpenRouter does NOT support.
- `LegacyOpenAIModel` — uses Chat Completions, which OpenRouter DOES support.

We use `LegacyOpenAIModel` and pass `base_url=https://openrouter.ai/api/v1`.

`FailoverLegacyOpenAIModel` (defined below) wraps the primary model with a
fallback model and catches the well-known OpenRouter quirk where a 200 OK is
returned with `choices=None` — MASFactory's stock adapter does
`response.choices[0]` immediately and raises TypeError → tenacity retries 3×
→ surfaces as `RetryError`. Recovery: invoke the fallback model.

The fallback's token tracker is read separately by `runner.py` so per-model
accounting in Supabase stays accurate.

v0.4.38 — when `Settings.reasoning_exclude` is true (default), every
chat-completion call carries `extra_body={"reasoning": {"exclude": true}}`.
OpenRouter strips reasoning tokens from the response server-side so the
model's visible body never contains a `<think>` wrapper. Required for the
Nemotron 3 Ultra primary; harmless on plain-instruct fallback models.
"""

from __future__ import annotations

from typing import Any

from masfactory import LegacyOpenAIModel

from .config import Settings


_REASONING_EXCLUDE_BODY: dict[str, dict[str, bool]] = {"reasoning": {"exclude": True}}


def _openrouter_kwargs(settings: Settings) -> dict:
    """OpenRouter recommends sending HTTP-Referer and X-Title for analytics.

    Also: a bounded timeout. The OpenAI SDK's default is 600 s per call;
    with MASFactory's tenacity retries (3×) and our failover (×2 models),
    one slow Nemotron call can hang the whole run for 60 min. Bound at 90 s.
    """
    return {
        "timeout": 90.0,
        "default_headers": {
            "HTTP-Referer": settings.http_referer,
            "X-Title": settings.app_title,
        },
    }


def _merge_extra_body(target: dict[str, Any] | None, addition: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge addition into target without mutating target."""
    if not target:
        return dict(addition)
    out = dict(target)
    for k, v in addition.items():
        if k not in out:
            out[k] = v
    return out


def _is_no_choices_error(exc: BaseException) -> bool:
    """Return True iff exc looks like the OpenRouter 200-no-choices quirk.

    Surface form: tenacity wraps three TypeErrors from
    `response.choices[0].message` into a RetryError. We check both the
    RetryError envelope and the underlying TypeError.
    """
    # Direct TypeError (no retries yet)
    if isinstance(exc, TypeError) and ("NoneType" in str(exc) or "subscriptable" in str(exc)):
        return True
    # tenacity.RetryError — class name check so we don't depend on tenacity here
    if type(exc).__name__ == "RetryError":
        # Most tenacity RetryErrors carry the last attempted result/exception
        last = getattr(exc, "last_attempt", None)
        if last is not None:
            try:
                inner = last.exception()
            except Exception:
                inner = None
            if inner is not None and isinstance(inner, TypeError):
                return True
        return True  # generic RetryError — try fallback anyway, can't make it worse
    return False


class FailoverLegacyOpenAIModel(LegacyOpenAIModel):
    """Primary LegacyOpenAIModel with an inner fallback model.

    On invocation, tries the primary first. If the call raises a TypeError
    (the OpenRouter no-choices quirk) or tenacity gives up with RetryError,
    falls back to a separately-configured fallback model.

    v0.4.38 — when `reasoning_exclude` is set, both primary and fallback
    requests carry `extra_body={"reasoning": {"exclude": true}}`. OpenRouter
    drops reasoning tokens from the response so the Nemotron 3 Ultra
    answer never reaches us inside a <think> wrapper.
    """

    def __init__(self, *, settings: Settings):
        super().__init__(
            model_name=settings.model_main,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            **_openrouter_kwargs(settings),
        )
        # Construct the fallback as a distinct LegacyOpenAIModel so its
        # token tracker is independent and the swap is process-safe.
        self._fallback = LegacyOpenAIModel(
            model_name=settings.model_fallback,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            **_openrouter_kwargs(settings),
        )
        self._failover_count: int = 0  # for audit / logging
        self._reasoning_exclude: bool = bool(settings.reasoning_exclude)

    @property
    def fallback(self) -> LegacyOpenAIModel:
        return self._fallback

    @property
    def failover_count(self) -> int:
        return self._failover_count

    @property
    def reasoning_exclude(self) -> bool:
        return self._reasoning_exclude

    def _apply_reasoning_exclude(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Inject extra_body={'reasoning': {'exclude': true}} into kwargs.

        Best-effort. masfactory's invoke forwards **kwargs to the OpenAI
        SDK's chat.completions.create, which honours `extra_body` as a
        per-call body-passthrough. If a future refactor drops the
        pass-through, the persister's L2 sanitisation still strips
        residual <think> wrappers.
        """
        if not self._reasoning_exclude:
            return kwargs
        new_kwargs = dict(kwargs)
        new_kwargs["extra_body"] = _merge_extra_body(
            kwargs.get("extra_body"), _REASONING_EXCLUDE_BODY,
        )
        return new_kwargs

    def invoke(self, messages: list[dict], tools: list[dict] | None, settings: dict | None = None, **kwargs: Any) -> dict:
        kwargs = self._apply_reasoning_exclude(kwargs)
        try:
            return super().invoke(messages, tools, settings, **kwargs)
        except Exception as exc:
            if _is_no_choices_error(exc):
                self._failover_count += 1
                return self._fallback.invoke(messages, tools, settings, **kwargs)
            raise


def build_main_model(settings: Settings) -> LegacyOpenAIModel:
    """Build the primary model with failover wired in.

    Return type is the parent class so callers can treat it as a normal
    LegacyOpenAIModel; the failover happens transparently.
    """
    return FailoverLegacyOpenAIModel(settings=settings)


def build_fallback_model(settings: Settings) -> LegacyOpenAIModel:
    """Standalone fallback model (kept for tests / inspection)."""
    return LegacyOpenAIModel(
        model_name=settings.model_fallback,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        **_openrouter_kwargs(settings),
    )
