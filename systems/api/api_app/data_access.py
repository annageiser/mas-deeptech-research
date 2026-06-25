"""Read-only Supabase access with a tiny in-process TTL cache.

No Streamlit here (unlike the old dashboard) — the API is a plain ASGI app.
The cache keeps the dashboard responsive without thrashing Supabase; TTL is
configurable via API_CACHE_TTL (default 60s).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
from supabase import Client, create_client

from .config import Settings, load_settings


_client: Optional[Client] = None
_cache: dict[str, tuple[float, Any]] = {}


def _settings() -> Settings:
    return load_settings()


def client() -> Client:
    global _client
    if _client is None:
        s = _settings()
        if not s.has_supabase:
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing in env")
        _client = create_client(s.supabase_url, s.supabase_service_key)
    return _client


def _cached(key: str, producer):
    ttl = _settings().cache_ttl_seconds
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and (now - hit[0]) < ttl:
        return hit[1]
    value = producer()
    _cache[key] = (now, value)
    return value


def _since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ---------- raw fetches ----------

def actors() -> pd.DataFrame:
    def _p():
        rows = client().table("actors").select(
            "slug,name,category,homepage,arxiv_query,notes"
        ).execute().data or []
        return pd.DataFrame(rows)
    return _cached("actors", _p)


def runs(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _p():
        q = (client().table("runs")
             # v0.4.36: include config_snapshot so /api/compare can split
             # per-system aggregates by model + tool_status. Hermes
             # records both into config_snapshot in v0.4.36+, so we can
             # tell "agent ran with tools and found nothing" apart from
             # "agent had no extraction tools available" days.
             .select("id,system,status,started_at,finished_at,actor_slugs,error_message,config_snapshot")
             .gte("started_at", _since_iso(days))
             .order("started_at", desc=True))
        if system:
            q = q.eq("system", system)
        return pd.DataFrame(q.execute().data or [])
    return _cached(f"runs:{system}:{days}", _p)


def signals(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _p():
        q = (client().table("signals")
             .select("id,run_id,actor_slug,system,source_kind,source_url,title,summary,"
                     "evidence_quote,dimension,is_technical,confidence,inserted_at,"
                     # v0.4.24 — VADER sentiment (NULL on legacy rows)
                     "sentiment_score,sentiment_label")
             .gte("inserted_at", _since_iso(days))
             .order("inserted_at", desc=True))
        if system:
            q = q.eq("system", system)
        return pd.DataFrame(q.execute().data or [])
    return _cached(f"signals:{system}:{days}", _p)


def signal_embeddings(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    """v0.4.40 — narrow (id, actor_slug, embedding) frame for the
    semantic-similarity edges in /api/knowledge-graph. Skipped from the
    main `signals()` query because the 768d vector(768) payload is
    ~6 KB per row and most callers do not need it.

    Filters to rows whose embedding is non-null. Returns an empty
    DataFrame if MASF_EMBEDDINGS / HRM_EMBEDDINGS are off everywhere
    (the default in `.env.example`).
    """
    def _p():
        q = (client().table("signals")
             .select("id,actor_slug,embedding")
             .gte("inserted_at", _since_iso(days))
             .not_.is_("embedding", "null"))
        if system:
            q = q.eq("system", system)
        return pd.DataFrame(q.execute().data or [])
    return _cached(f"signal_embeddings:{system}:{days}", _p)


def token_usage(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _p():
        rows = (client().table("token_usage")
                .select("run_id,node_name,model_name,input_tokens,output_tokens,calls,recorded_at")
                .gte("recorded_at", _since_iso(days)).execute().data or [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        run_ids = list({r for r in df["run_id"].dropna().tolist()})
        runs_df = pd.DataFrame(
            client().table("runs").select("id,system").in_("id", run_ids).execute().data or []
        )
        if runs_df.empty:
            df["system"] = None
        else:
            df = df.merge(runs_df, left_on="run_id", right_on="id", how="left").drop(columns=["id"], errors="ignore")
        if system:
            df = df[df["system"] == system]
        return df
    return _cached(f"tokens:{system}:{days}", _p)
