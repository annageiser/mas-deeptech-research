"""Runtime configuration for the reports container."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# v0.4.36 — unified with both systems. Was Nemotron-Super-120B which is a
# REASONING model: openrouter.py:81 took choices[0].message.content raw,
# so the entire <think>...</think> block appeared as visible text in every
# daily report (unreadable output flagged by user). Switching to Qwen3 Next
# (plain instruct, see docs/iterations/v0.4.36-model-unification.md)
# removes the bleed at the source. The _strip_reasoning_tags helper in
# openrouter.py is the belt-and-braces defence in case a future reports
# model is silently swapped to a reasoning variant.
DEFAULT_MODEL_MAIN = "qwen/qwen3-next-80b-a3b-instruct:free"
DEFAULT_MODEL_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"
DEFAULT_REPORTS_DIR = "/data/reports"
DEFAULT_REPO_DIR = "/repo"
DEFAULT_THESIS_NOTES_PATH = "/data/raw/thesis_notes.md"
DEFAULT_APP_TITLE = "Reports (BSc thesis)"
DEFAULT_HTTP_REFERER = "https://github.com/anna-geiser/mas-deeptech-research"


class ConfigError(RuntimeError):
    """Raised when required env config is missing."""


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_base_url: str
    model_main: str
    model_fallback: str
    supabase_url: str
    supabase_service_key: str
    reports_dir: str
    repo_dir: str
    thesis_notes_path: str
    http_referer: str
    app_title: str

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


def _require(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise ConfigError(f"environment variable {name} is required")
    return v


def load_settings(*, require_supabase: bool = True) -> Settings:
    openrouter_key = _require("OPENROUTER_API_KEY")
    supabase_url = _require("SUPABASE_URL") if require_supabase else os.environ.get("SUPABASE_URL", "")
    supabase_key = _require("SUPABASE_SERVICE_KEY") if require_supabase else os.environ.get("SUPABASE_SERVICE_KEY", "")

    return Settings(
        openrouter_api_key=openrouter_key,
        openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()
        or DEFAULT_OPENROUTER_BASE_URL,
        model_main=os.environ.get(
            "RPT_MODEL_MAIN",
            os.environ.get("MASF_MODEL_MAIN", DEFAULT_MODEL_MAIN),
        ).strip()
        or DEFAULT_MODEL_MAIN,
        model_fallback=os.environ.get(
            "RPT_MODEL_FALLBACK",
            os.environ.get("MASF_MODEL_FALLBACK", DEFAULT_MODEL_FALLBACK),
        ).strip()
        or DEFAULT_MODEL_FALLBACK,
        supabase_url=supabase_url,
        supabase_service_key=supabase_key,
        reports_dir=os.environ.get("RPT_REPORTS_DIR", DEFAULT_REPORTS_DIR).strip() or DEFAULT_REPORTS_DIR,
        repo_dir=os.environ.get("RPT_REPO_DIR", DEFAULT_REPO_DIR).strip() or DEFAULT_REPO_DIR,
        thesis_notes_path=os.environ.get("RPT_THESIS_NOTES_PATH", DEFAULT_THESIS_NOTES_PATH).strip()
        or DEFAULT_THESIS_NOTES_PATH,
        http_referer=os.environ.get("OPENROUTER_HTTP_REFERER", DEFAULT_HTTP_REFERER).strip()
        or DEFAULT_HTTP_REFERER,
        app_title=os.environ.get("OPENROUTER_APP_TITLE", DEFAULT_APP_TITLE).strip() or DEFAULT_APP_TITLE,
    )
