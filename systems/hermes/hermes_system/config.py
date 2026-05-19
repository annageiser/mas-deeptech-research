"""Runtime configuration loaded from environment variables.

Mirrors systems/masfactory/masfactory_system/config.py so the two systems'
operational surface is identical (same env-var names where possible). The
env vars not shared between systems are namespaced with HRM_ instead of MASF_.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL_MAIN = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_MODEL_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"
DEFAULT_HTTP_REFERER = "https://github.com/anna-geiser/mas-deeptech-research"
DEFAULT_APP_TITLE = "Hermes System B (BSc thesis)"

DEFAULT_SKILLS_DIR = "/app/skills"
DEFAULT_MEMORY_PATH = "/data/raw/hermes_memory.sqlite"
DEFAULT_AUDIT_DIR = "/data/raw/runs"


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
    max_iterations_per_actor: int
    skills_dir: str
    memory_path: str
    audit_dir: str
    http_referer: str
    app_title: str

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


def load_settings(*, require_supabase: bool = True) -> Settings:
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
        model_main=os.environ.get("HRM_MODEL_MAIN", os.environ.get("MASF_MODEL_MAIN", DEFAULT_MODEL_MAIN)).strip()
        or DEFAULT_MODEL_MAIN,
        model_fallback=os.environ.get(
            "HRM_MODEL_FALLBACK",
            os.environ.get("MASF_MODEL_FALLBACK", DEFAULT_MODEL_FALLBACK),
        ).strip()
        or DEFAULT_MODEL_FALLBACK,
        supabase_url=supabase_url,
        supabase_service_key=supabase_key,
        limit_actors=_int("HRM_LIMIT_ACTORS", 3),
        max_iterations_per_actor=_int("HRM_MAX_ITERATIONS", 6),
        skills_dir=os.environ.get("HRM_SKILLS_DIR", DEFAULT_SKILLS_DIR).strip() or DEFAULT_SKILLS_DIR,
        memory_path=os.environ.get("HRM_MEMORY_PATH", DEFAULT_MEMORY_PATH).strip() or DEFAULT_MEMORY_PATH,
        audit_dir=os.environ.get("HRM_AUDIT_DIR", DEFAULT_AUDIT_DIR).strip() or DEFAULT_AUDIT_DIR,
        http_referer=os.environ.get("OPENROUTER_HTTP_REFERER", DEFAULT_HTTP_REFERER).strip()
        or DEFAULT_HTTP_REFERER,
        app_title=os.environ.get("OPENROUTER_APP_TITLE", DEFAULT_APP_TITLE).strip() or DEFAULT_APP_TITLE,
    )
