"""Cached Supabase reads for the dashboard.

Everything in here is read-only. We don't even instantiate the writer-side
of supabase-py; queries go via the REST client with the service_role key.
A 60-second TTL cache keeps Streamlit responsive without thrashing the DB.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

import pandas as pd
import streamlit as st
from supabase import Client, create_client


def _settings() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing in container env")
    return url, key


@st.cache_resource(show_spinner=False)
def _client() -> Client:
    url, key = _settings()
    return create_client(url, key)


@st.cache_data(ttl=60, show_spinner=False)
def actors() -> pd.DataFrame:
    rows = _client().table("actors").select("slug,name,category,homepage,arxiv_query,notes").execute().data or []
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def runs(system: Optional[str] = None, days: int = 30) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = _client().table("runs").select("id,system,status,started_at,finished_at,actor_slugs,error_message").gte("started_at", since).order("started_at", desc=True)
    if system:
        q = q.eq("system", system)
    rows = q.execute().data or []
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def signals(system: Optional[str] = None, days: int = 30) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = (
        _client()
        .table("signals")
        .select("id,run_id,actor_slug,system,source_kind,source_url,title,summary,evidence_quote,dimension,is_technical,confidence,inserted_at")
        .gte("inserted_at", since)
        .order("inserted_at", desc=True)
    )
    if system:
        q = q.eq("system", system)
    rows = q.execute().data or []
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def token_usage(system: Optional[str] = None, days: int = 30) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # token_usage doesn't have system column directly; join via runs.
    tk_rows = _client().table("token_usage").select("run_id,node_name,model_name,input_tokens,output_tokens,calls,recorded_at").gte("recorded_at", since).execute().data or []
    if not tk_rows:
        return pd.DataFrame()
    df = pd.DataFrame(tk_rows)
    # Pull the system per run
    run_ids = list(set(df["run_id"].dropna().tolist()))
    runs_df = pd.DataFrame(_client().table("runs").select("id,system").in_("id", run_ids).execute().data or [])
    if runs_df.empty:
        df["system"] = None
    else:
        df = df.merge(runs_df, left_on="run_id", right_on="id", how="left").drop(columns=["id"], errors="ignore")
    if system:
        df = df[df["system"] == system]
    return df


def reports_dir() -> str:
    return os.environ.get("DASH_REPORTS_DIR", "/data/reports")
