"""Read-only Supabase access with a tiny in-process TTL cache.

The API is a plain ASGI app. The cache keeps the frontend responsive without
thrashing Supabase; TTL is configurable via API_CACHE_TTL (default 60s).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

try:
    from supabase import Client, create_client
except ImportError:
    Client = None
    create_client = None

from .config import Settings, load_settings


log = logging.getLogger(__name__)

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


# ---------- pagination ----------
#
# PostgREST applies a server-side `max-rows` cap (1000 on Supabase) and returns
# a PARTIAL result with no error when a query would exceed it. Every fetch below
# used to call .execute() unranged, so once a table passed 1000 matching rows the
# extra rows were dropped silently. With `order=inserted_at.desc` that meant the
# newest 1000 rows were kept and everything older vanished — not a random sample,
# and the bias tracked each system's recent output rate.
#
# `_paged` walks the result with explicit .range() windows until the row count
# reaches the server's own exact count. Callers pass a BUILDER FUNCTION rather
# than a query object because .range() mutates the builder, so each page needs a
# fresh one.

PAGE_SIZE = 1000
# Safety stop so a runaway count can never spin forever. Well above the corpus
# size this project produces (a few thousand signals per evaluation window).
MAX_ROWS = 200_000


def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    """Drop rows repeated across page boundaries.

    Paging is stable because every query orders by a unique tiebreaker, but a
    concurrent insert between two page requests can still shift the window. The
    id-based pass makes that harmless for the tables that have an `id`; tables
    keyed on something else (actors) pass through untouched.
    """
    seen: set = set()
    out: list[dict] = []
    for row in rows:
        rid = row.get("id") if isinstance(row, dict) else None
        if rid is None:
            out.append(row)
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def _paged(build, *, page_size: int = PAGE_SIZE, max_rows: int = MAX_ROWS) -> list[dict]:
    """Collect every row a query matches, one .range() window at a time.

    `build` must return a FRESH query builder whose .select() carries
    count="exact", so the first response tells us how many rows exist in total
    and no extra probe request is needed when the result fits in one page.
    """
    first = build().range(0, page_size - 1).execute()
    rows: list[dict] = list(first.data or [])
    total = getattr(first, "count", None)

    if total is not None:
        # Exact count from the server: page straight to it, no probing.
        target = min(int(total), max_rows)
        while len(rows) < target:
            # Clamp the last window so the safety cap is exact rather than
            # overshooting by up to a page.
            span = min(page_size, target - len(rows))
            chunk = build().range(len(rows), len(rows) + span - 1).execute().data or []
            if not chunk:
                break
            rows.extend(chunk)
        if total > max_rows:
            log.warning(
                "_paged hit the %d-row safety cap (server reported %d matching rows); "
                "result is truncated", max_rows, total,
            )
        return _dedupe_by_id(rows)

    # No count header. Treat a short page as the end, which is the same rule the
    # first page already implies: had the server capped us below page_size, page
    # one would have come back short too.
    while len(rows) < max_rows and len(rows) % page_size == 0 and rows:
        span = min(page_size, max_rows - len(rows))
        chunk = build().range(len(rows), len(rows) + span - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < span:
            break
    if len(rows) >= max_rows:
        log.warning("_paged hit the %d-row safety cap; result may be truncated", max_rows)
    return _dedupe_by_id(rows)


# ---------- raw fetches ----------

def actors() -> pd.DataFrame:
    def _p():
        rows = _paged(lambda: (
            client().table("actors")
            .select("slug,name,category,homepage,arxiv_query,notes", count="exact")
            .order("slug")
        ))
        return pd.DataFrame(rows)
    return _cached("actors", _p)


def runs(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _build():
        q = (client().table("runs")
             # v0.4.36: include config_snapshot so /api/compare can split
             # per-system aggregates by model + tool_status. Hermes
             # records both into config_snapshot in v0.4.36+, so we can
             # tell "agent ran with tools and found nothing" apart from
             # "agent had no extraction tools available" days.
             .select("id,system,status,started_at,finished_at,actor_slugs,error_message,config_snapshot",
                     count="exact")
             .gte("started_at", _since_iso(days))
             # `id` is the tiebreaker that makes paging deterministic when two
             # runs share a started_at.
             .order("started_at", desc=True)
             .order("id"))
        if system:
            q = q.eq("system", system)
        return q
    return _cached(f"runs:{system}:{days}", lambda: pd.DataFrame(_paged(_build)))


def signals(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _build():
        q = (client().table("signals")
             .select("id,run_id,actor_slug,system,source_kind,source_url,title,summary,"
                     "evidence_quote,dimension,is_technical,confidence,inserted_at,"
                     # v0.4.24 — VADER sentiment (NULL on legacy rows)
                     "sentiment_score,sentiment_label",
                     count="exact")
             .gte("inserted_at", _since_iso(days))
             # A whole cron tick lands with near-identical inserted_at values,
             # so `id` is required here for pages not to overlap or skip.
             .order("inserted_at", desc=True)
             .order("id"))
        if system:
            q = q.eq("system", system)
        return q
    return _cached(f"signals:{system}:{days}", lambda: pd.DataFrame(_paged(_build)))


def signal_embeddings(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    """v0.4.40 — narrow (id, actor_slug, embedding) frame for the
    semantic-similarity edges in /api/knowledge-graph. Skipped from the
    main `signals()` query because the 768d vector(768) payload is
    ~6 KB per row and most callers do not need it.

    Filters to rows whose embedding is non-null. Returns an empty
    DataFrame if MASF_EMBEDDINGS / HRM_EMBEDDINGS are off everywhere
    (the default in `.env.example`).
    """
    def _build():
        q = (client().table("signals")
             .select("id,actor_slug,embedding", count="exact")
             .gte("inserted_at", _since_iso(days))
             .not_.is_("embedding", "null")
             .order("id"))
        if system:
            q = q.eq("system", system)
        return q
    return _cached(f"signal_embeddings:{system}:{days}",
                   lambda: pd.DataFrame(_paged(_build)))


def token_usage(system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _p():
        rows = _paged(lambda: (
            client().table("token_usage")
            .select("run_id,node_name,model_name,input_tokens,output_tokens,calls,recorded_at",
                    count="exact")
            .gte("recorded_at", _since_iso(days))
            .order("id")
        ))
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        run_ids = list({r for r in df["run_id"].dropna().tolist()})
        # PostgREST puts the IN list in the URL, so a long run_id set can blow
        # the URL length limit. Chunk it the way eval_app already does.
        run_rows: list[dict] = []
        for i in range(0, len(run_ids), 100):
            chunk = run_ids[i:i + 100]
            run_rows.extend(_paged(lambda c=chunk: (
                client().table("runs").select("id,system", count="exact").in_("id", c).order("id")
            )))
        runs_df = pd.DataFrame(run_rows)
        if runs_df.empty:
            df["system"] = None
        else:
            df = df.merge(runs_df, left_on="run_id", right_on="id", how="left").drop(columns=["id"], errors="ignore")
        if system:
            df = df[df["system"] == system]
        return df
    return _cached(f"tokens:{system}:{days}", _p)
