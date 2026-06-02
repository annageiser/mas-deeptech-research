"""Read-only Supabase access. Vendored from systems/api/api_app/data_access.py
(same shape, no cache layer — the harness runs to completion and exits).

Independent module rather than an import so the eval package stays runnable
without systems/api as a peer dependency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from supabase import Client, create_client

from .config import Settings, load_settings


_client: Optional[Client] = None


def client() -> Client:
    global _client
    if _client is None:
        s = load_settings()
        if not s.has_supabase:
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing in env")
        _client = create_client(s.supabase_url, s.supabase_service_key)
    return _client


def _since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def actors() -> pd.DataFrame:
    rows = client().table("actors").select(
        "slug,name,category,homepage,arxiv_query,notes"
    ).execute().data or []
    return pd.DataFrame(rows)


def runs(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    q = (client().table("runs")
         .select("id,system,status,started_at,finished_at,actor_slugs,error_message")
         .gte("started_at", _since_iso(days))
         .order("started_at", desc=True))
    if system:
        q = q.eq("system", system)
    return pd.DataFrame(q.execute().data or [])


def signals(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    q = (client().table("signals")
         .select("id,run_id,actor_slug,system,source_kind,source_url,title,summary,"
                 "evidence_quote,dimension,signal_type,dimension_legacy,is_technical,"
                 "confidence,inserted_at")
         .gte("inserted_at", _since_iso(days))
         .order("inserted_at", desc=True))
    if system:
        q = q.eq("system", system)
    return pd.DataFrame(q.execute().data or [])


def token_usage(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    # token_usage doesn't carry `system` directly — join via runs.
    runs_df = runs(system=system, days=days)
    if runs_df.empty:
        return pd.DataFrame(columns=["run_id", "node_name", "model_name",
                                     "input_tokens", "output_tokens", "calls"])
    run_ids = runs_df["id"].tolist()
    # Supabase REST limits IN-clauses; chunk if needed (rare at our volume).
    rows: list[dict] = []
    CHUNK = 100
    for i in range(0, len(run_ids), CHUNK):
        chunk = run_ids[i:i + CHUNK]
        resp = (client().table("token_usage")
                .select("run_id,node_name,model_name,input_tokens,output_tokens,calls")
                .in_("run_id", chunk)
                .execute())
        rows.extend(resp.data or [])
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.merge(runs_df[["id", "system"]].rename(columns={"id": "run_id"}),
                      on="run_id", how="left")
    return df
