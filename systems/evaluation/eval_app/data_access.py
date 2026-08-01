"""Read-only Supabase access. Vendored from systems/api/api_app/data_access.py
(same shape, no cache layer — the harness runs to completion and exits).

Independent module rather than an import so the eval package stays runnable
without systems/api as a peer dependency."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from supabase import Client, create_client

from .config import Settings, load_settings


log = logging.getLogger(__name__)

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


# ---------- pagination ----------
#
# Vendored alongside the api_app copy for the same reason the rest of this
# module is (no systems/api peer dependency), and it matters more here: the
# harness computes every thesis metric off these frames.
#
# PostgREST caps a response at `max-rows` (1000 on Supabase) and returns a
# PARTIAL result with no error. An unranged query over a 90-day window that
# holds several thousand signals therefore silently evaluated a recency-skewed
# third of the corpus. `_paged` walks .range() windows to the server's exact
# count instead. `build` must return a FRESH builder each call, because
# .range() mutates it.

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


def actors() -> pd.DataFrame:
    rows = _paged(lambda: (
        client().table("actors")
        .select("slug,name,category,homepage,arxiv_query,notes", count="exact")
        .order("slug")
    ))
    return pd.DataFrame(rows)


def runs(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _build():
        q = (client().table("runs")
             .select("id,system,status,started_at,finished_at,actor_slugs,error_message",
                     count="exact")
             .gte("started_at", _since_iso(days))
             .order("started_at", desc=True)
             .order("id"))
        if system:
            q = q.eq("system", system)
        return q
    return pd.DataFrame(_paged(_build))


def signals(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    def _build():
        q = (client().table("signals")
             .select("id,run_id,actor_slug,system,source_kind,source_url,title,summary,"
                     "evidence_quote,dimension,signal_type,dimension_legacy,is_technical,"
                     "confidence,inserted_at",
                     count="exact")
             .gte("inserted_at", _since_iso(days))
             # `id` is the tiebreaker: a cron tick inserts hundreds of rows with
             # near-identical inserted_at, so ordering on it alone is not stable
             # enough to page over.
             .order("inserted_at", desc=True)
             .order("id"))
        if system:
            q = q.eq("system", system)
        return q
    return pd.DataFrame(_paged(_build))


def token_usage(*, system: Optional[str] = None, days: int = 90) -> pd.DataFrame:
    # token_usage doesn't carry `system` directly — join via runs.
    runs_df = runs(system=system, days=days)
    if runs_df.empty:
        return pd.DataFrame(columns=["run_id", "node_name", "model_name",
                                     "input_tokens", "output_tokens", "calls"])
    run_ids = runs_df["id"].tolist()
    # Supabase REST limits IN-clauses; chunk if needed (rare at our volume).
    # Each chunk is additionally paged: 100 runs of a multi-node graph can
    # exceed the 1000-row response cap on their own.
    rows: list[dict] = []
    CHUNK = 100
    for i in range(0, len(run_ids), CHUNK):
        chunk = run_ids[i:i + CHUNK]
        rows.extend(_paged(lambda c=chunk: (
            client().table("token_usage")
            .select("run_id,node_name,model_name,input_tokens,output_tokens,calls",
                    count="exact")
            .in_("run_id", c)
            .order("id")
        )))
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.merge(runs_df[["id", "system"]].rename(columns={"id": "run_id"}),
                      on="run_id", how="left")
    return df
