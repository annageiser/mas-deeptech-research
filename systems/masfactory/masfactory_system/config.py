"""Runtime configuration loaded from environment variables.

All env vars are documented in the repo-root `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# v0.4.38 — both systems migrated to nvidia/nemotron-3-ultra-550b-a55b:free
# (a reasoning model on OpenRouter's free tier). System A handles the
# <think> wrapper via the OpenRouter `reasoning: {exclude: true}` body
# field (see model.py); the Instructor-backed structured-output layer
# also tolerates leading non-JSON content. Fallback is a plain-instruct
# free model so a rate-limit or provider outage cannot blank a run.
# See docs/iterations/v0.4.38-nemotron-3-ultra-migration.md.
DEFAULT_MODEL_MAIN = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_MODEL_FALLBACK = "qwen/qwen3-next-80b-a3b-instruct:free"
DEFAULT_HTTP_REFERER = "https://github.com/anna-geiser/mas-deeptech-research"
DEFAULT_APP_TITLE = "MASFactory System A (BSc thesis)"


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_base_url: str
    model_main: str
    model_fallback: str
    supabase_url: str
    supabase_service_key: str
    limit_actors: int
    limit_arxiv_per_actor: int
    limit_website_pages_per_actor: int
    limit_news_per_actor: int
    audit_dir: str
    http_referer: str
    app_title: str
    # v0.4.38 — when true, every chat-completion request to OpenRouter
    # carries `extra_body={"reasoning": {"exclude": true}}` so reasoning
    # models (Nemotron 3 Ultra) return their answer outside the <think>
    # wrapper. Forwarded into the run's config_snapshot for replay.
    reasoning_exclude: bool

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"environment variable {name} is required")
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"environment variable {name} must be an integer, got {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def load_settings(*, require_supabase: bool = True) -> Settings:
    """Build a Settings object from the current environment.

    `require_supabase=False` lets the build-time smoke test compile the graph
    without DB credentials present in the image.
    """
    openrouter_key = _require("OPENROUTER_API_KEY")

    if require_supabase:
        supabase_url = _require("SUPABASE_URL")
        supabase_key = _require("SUPABASE_SERVICE_KEY")
    else:
        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

    return Settings(
        openrouter_api_key=openrouter_key,
        openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()
        or DEFAULT_OPENROUTER_BASE_URL,
        model_main=os.environ.get("MASF_MODEL_MAIN", DEFAULT_MODEL_MAIN).strip() or DEFAULT_MODEL_MAIN,
        model_fallback=os.environ.get("MASF_MODEL_FALLBACK", DEFAULT_MODEL_FALLBACK).strip()
        or DEFAULT_MODEL_FALLBACK,
        supabase_url=supabase_url,
        supabase_service_key=supabase_key,
        limit_actors=_int("MASF_LIMIT_ACTORS", 3),
        limit_arxiv_per_actor=_int("MASF_LIMIT_ARXIV", 5),
        limit_website_pages_per_actor=_int("MASF_LIMIT_WEBSITE", 3),
        limit_news_per_actor=_int("MASF_LIMIT_NEWS", 5),
        audit_dir=os.environ.get("MASF_AUDIT_DIR", "/data/raw/runs").strip() or "/data/raw/runs",
        http_referer=os.environ.get("OPENROUTER_HTTP_REFERER", DEFAULT_HTTP_REFERER).strip()
        or DEFAULT_HTTP_REFERER,
        app_title=os.environ.get("OPENROUTER_APP_TITLE", DEFAULT_APP_TITLE).strip() or DEFAULT_APP_TITLE,
        reasoning_exclude=_bool("MASF_REASONING_EXCLUDE", True),
    )
