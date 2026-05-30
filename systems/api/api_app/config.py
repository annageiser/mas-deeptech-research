"""Runtime configuration for the API service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_key: str
    reports_dir: str
    schema_path: str
    cache_ttl_seconds: int
    cors_origins: list[str]

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


def load_settings() -> Settings:
    raw_origins = os.environ.get("API_CORS_ORIGINS", "*").strip()
    origins = ["*"] if raw_origins == "*" else [o.strip() for o in raw_origins.split(",") if o.strip()]
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", "").strip(),
        reports_dir=os.environ.get("API_REPORTS_DIR", "/data/reports").strip() or "/data/reports",
        schema_path=os.environ.get(
            "API_SCHEMA_PATH", "/app/schema.yaml"
        ).strip() or "/app/schema.yaml",
        cache_ttl_seconds=int(os.environ.get("API_CACHE_TTL", "60") or "60"),
        cors_origins=origins,
    )
