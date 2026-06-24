"""Propagate manual_signals into public.signals (v0.4.37).

Anna curates signals through /labels (CRUD over public.manual_signals).
This script reads any rows that haven't been propagated yet and inserts
them into public.signals with system='manual' and source_kind='manual'
so they appear on /signals, /compare, and the daily reports under their
own slice — alongside the masfactory + hermes producers.

Idempotency:
  * manual_signals.propagated_signal_id is set when propagation
    completes. Re-running this script is a no-op for already-propagated
    rows.
  * If propagation later fails because the actor_slug column changed,
    we leave propagated_signal_id NULL so the next run retries.

Run modes:
  * Standalone: `python -m masfactory_system.scripts.sync_manual_signals`
    (or via Docker — see docker-compose.yml and the chained cron).
  * After-write hook: API can call this script as a subprocess after
    each POST/PATCH on manual signals so the propagation is near-real-time.

Note on `actor_slug`: the canonical public.signals table requires a
single actor_slug per row. If a manual signal lists multiple related
actors, we insert one signal row per actor (each sharing the same
source_url + title but differing in actor_slug). The `propagated_signal_id`
column on manual_signals stores the FIRST inserted row's id only — we
don't try to track a multi-row fan-out.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


_SYNTHETIC_RUN_LABEL = "manual-sync"


def _supabase_env() -> tuple[str, str]:
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (base and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        sys.exit(2)
    return base.rstrip("/"), key


def _headers(api_key: str, *, prefer: str = "return=representation") -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _content_hash(actor_slug: str, source_url: str, title: str) -> str:
    """Same formula as both persisters (v0.4.36)."""
    blob = "|".join([
        (actor_slug or "").strip().lower(),
        (source_url or "").strip().lower(),
        (title or "").strip().lower(),
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ensure_synthetic_run(base: str, key: str) -> str:
    """Get-or-create a single long-lived public.runs row for the manual
    producer. All propagated manual signals attach to this run so they
    have a valid run_id (the public.signals FK requires it).

    Lookup is by config_snapshot.label = 'manual-sync'.
    """
    with httpx.Client(timeout=15.0) as client:
        # Try to find an existing one.
        resp = client.get(
            f"{base}/rest/v1/runs",
            params={
                "system": "eq.manual",
                "config_snapshot->>label": f"eq.{_SYNTHETIC_RUN_LABEL}",
                "select": "id",
                "limit": "1",
            },
            headers=_headers(key),
        )
        if resp.is_success and resp.json():
            return resp.json()[0]["id"]
        # Create.
        row = {
            "system": "manual",
            "status": "ok",
            "config_snapshot": {
                "label": _SYNTHETIC_RUN_LABEL,
                "note": "synthetic run for manual-signal propagation (v0.4.37)",
            },
            "actor_slugs": [],
        }
        resp = client.post(
            f"{base}/rest/v1/runs",
            headers=_headers(key),
            json=row,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0]["id"]


def _fetch_pending(base: str, key: str, *, limit: int = 500) -> list[dict[str, Any]]:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{base}/rest/v1/manual_signals",
            params={
                "select": "*",
                "propagated_signal_id": "is.null",
                "order": "created_at.asc",
                "limit": str(limit),
            },
            headers=_headers(key),
        )
        resp.raise_for_status()
        return resp.json() or []


def _existing_actor_slugs(base: str, key: str) -> set[str]:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{base}/rest/v1/actors",
            params={"select": "slug", "limit": "1000"},
            headers=_headers(key),
        )
        if not resp.is_success:
            return set()
        return {r["slug"] for r in (resp.json() or [])}


def _insert_signal_rows(
    base: str, key: str, *, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    url = f"{base}/rest/v1/signals?on_conflict=actor_slug,source_url,content_hash"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            headers=_headers(key, prefer="resolution=ignore-duplicates,return=representation"),
            json=rows,
        )
        resp.raise_for_status()
        return resp.json() or []


def _mark_propagated(
    base: str, key: str, *, manual_id: str, signal_id: Optional[str]
) -> None:
    payload = {
        "propagated_signal_id": signal_id,
        "propagated_at": datetime.now(timezone.utc).isoformat(),
    }
    with httpx.Client(timeout=15.0) as client:
        client.patch(
            f"{base}/rest/v1/manual_signals",
            params={"id": f"eq.{manual_id}"},
            headers=_headers(key, prefer="return=minimal"),
            json=payload,
        )


def main() -> int:
    base, key = _supabase_env()

    pending = _fetch_pending(base, key)
    if not pending:
        print("[sync_manual_signals] no pending manual signals.")
        return 0

    run_id = _ensure_synthetic_run(base, key)
    valid_actors = _existing_actor_slugs(base, key)

    total_inserted = 0
    for m in pending:
        title = (m.get("title") or m.get("source_url") or "(untitled manual signal)").strip()
        summary = (m.get("notes") or "").strip() or "Hand-curated signal added through /labels."
        actor_slugs = [s for s in (m.get("actor_slugs") or []) if s in valid_actors]
        # If no related actors, fall back to a synthetic 'unattributed' actor
        # only if it exists; otherwise skip (manual signals without a related
        # actor are still useful as few-shot examples — they just don't
        # appear in /signals).
        if not actor_slugs:
            _mark_propagated(base, key, manual_id=m["id"], signal_id=None)
            continue

        rows: list[dict[str, Any]] = []
        for actor_slug in actor_slugs:
            rows.append({
                "run_id": run_id,
                "actor_slug": actor_slug,
                "system": "manual",
                "source_kind": "manual",
                "source_url": m["source_url"],
                "title": title[:500],
                "summary": summary[:2000],
                "evidence_quote": (m.get("notes") or title)[:500],
                "dimension": (m.get("dimension") or "manual_entry"),
                "signal_type": m.get("signal_type"),
                "is_technical": False,
                "confidence": 1.0,  # Anna asserted it
                "content_hash": _content_hash(actor_slug, m["source_url"], title),
                "observed_at": m.get("created_at"),
            })
        try:
            inserted = _insert_signal_rows(base, key, rows=rows)
        except httpx.HTTPStatusError as exc:
            print(
                f"[sync_manual_signals] insert failed for {m.get('id')}: "
                f"HTTP {exc.response.status_code} {exc.response.text[:200]}",
                file=sys.stderr,
            )
            continue

        first_id = inserted[0]["id"] if inserted else None
        _mark_propagated(base, key, manual_id=m["id"], signal_id=first_id)
        total_inserted += len(inserted)
        print(
            f"[sync_manual_signals] propagated {m.get('id')} "
            f"({len(rows)} actor rows → {len(inserted)} inserted)"
        )

    print(f"[sync_manual_signals] done — {total_inserted} signal rows inserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
