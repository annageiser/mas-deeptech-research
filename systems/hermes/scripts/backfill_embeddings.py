#!/usr/bin/env python3
"""Backfill embeddings on existing System B (hermes) signals.

Prereq for M.1 (task #113) — semantic dedup is only meaningful once
both systems have embedding coverage on the historical corpus.

This script:
  1. Pages through public.signals WHERE system='hermes' AND embedding IS NULL
  2. Computes the 768d BGE embedding using the SAME model + composition
     as the live persister (so the backfilled values match what new
     inserts produce)
  3. PATCH-updates each row via Supabase REST API in batches of 50

Run inside the Hermes wrapper container so fastembed is available:

    docker compose run --rm \\
        -e HRM_EMBEDDINGS=1 \\
        --entrypoint python hermes \\
        /opt/swiss-quantum/scripts/backfill_embeddings.py

Or with explicit dry-run / limit for testing:

    ... backfill_embeddings.py --dry-run --limit 10

Output: one line per batch ("N rows embedded, M failures"), final
summary on stderr. Idempotent: re-running after partial completion
just picks up where it left off (the WHERE embedding IS NULL filter).

No imports from masfactory_system — comparison-validity invariant.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import httpx

# Vendored from persist_signals.py so the backfill never drifts from
# the live insert path. If you change one, change the other.
_EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"
_EMBEDDING_DIM = 768
_embedding_model: Any = None


def _embed_text(text: str) -> list[float] | None:
    global _embedding_model
    if not text or not text.strip():
        return None
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            print("FATAL: fastembed not installed in this container — "
                  "run inside the Hermes wrapper image", file=sys.stderr)
            sys.exit(2)
        _embedding_model = TextEmbedding(model_name=_EMBEDDING_MODEL_NAME)
    try:
        gen = _embedding_model.embed([text.strip()])
        vec = list(next(gen))
        return vec if len(vec) == _EMBEDDING_DIM else None
    except Exception as exc:
        print(f"  embed failed: {exc}", file=sys.stderr)
        return None


def _compose_signal_text(signal: dict[str, Any]) -> str:
    parts = [
        signal.get("title") or "",
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
        f"dimension:{signal.get('dimension') or 'unknown'}",
    ]
    return "\n".join(p.strip() for p in parts if p.strip())


def _supabase_env() -> tuple[str, str]:
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (base and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        sys.exit(2)
    return base, key


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _fetch_batch(client: httpx.Client, base: str, headers: dict, batch_size: int) -> list[dict]:
    """Get up to batch_size hermes rows still lacking an embedding."""
    url = (f"{base.rstrip('/')}/rest/v1/signals"
           f"?system=eq.hermes&embedding=is.null"
           f"&select=id,title,summary,evidence_quote,dimension"
           f"&limit={batch_size}&order=inserted_at.asc")
    r = client.get(url, headers=headers)
    r.raise_for_status()
    return r.json() or []


def _update_one(client: httpx.Client, base: str, headers: dict,
                row_id: str, vec: list[float]) -> bool:
    url = f"{base.rstrip('/')}/rest/v1/signals?id=eq.{row_id}"
    body = {"embedding": vec}
    try:
        r = client.patch(url, headers={**headers, "Prefer": "return=minimal"}, json=body)
        r.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        print(f"  PATCH {row_id}: HTTP {exc.response.status_code} {exc.response.text[:200]}",
              file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Rows per fetch (default 50; max 1000)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after this many rows total (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute embeddings but skip UPDATE")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="Seconds to sleep between rows (default 0)")
    args = parser.parse_args(argv)

    if args.batch_size < 1 or args.batch_size > 1000:
        print("--batch-size must be 1..1000", file=sys.stderr)
        return 2

    base, key = _supabase_env()
    headers = _headers(key)

    total_processed = 0
    total_updated = 0
    total_failed = 0

    with httpx.Client(timeout=60.0) as client:
        while True:
            if args.limit and total_processed >= args.limit:
                break
            batch_size = (min(args.batch_size, args.limit - total_processed)
                          if args.limit else args.batch_size)
            try:
                rows = _fetch_batch(client, base, headers, batch_size)
            except httpx.HTTPStatusError as exc:
                print(f"FATAL: fetch failed: HTTP {exc.response.status_code} "
                      f"{exc.response.text[:200]}", file=sys.stderr)
                return 1
            if not rows:
                break

            batch_updated = 0
            batch_failed = 0
            for row in rows:
                text = _compose_signal_text(row)
                vec = _embed_text(text)
                if vec is None:
                    batch_failed += 1
                    total_failed += 1
                    continue
                if args.dry_run:
                    batch_updated += 1
                    total_updated += 1
                else:
                    if _update_one(client, base, headers, row["id"], vec):
                        batch_updated += 1
                        total_updated += 1
                    else:
                        batch_failed += 1
                        total_failed += 1
                total_processed += 1
                if args.sleep > 0:
                    time.sleep(args.sleep)
            print(f"batch: fetched={len(rows)} updated={batch_updated} "
                  f"failed={batch_failed}  running total: processed={total_processed} "
                  f"updated={total_updated} failed={total_failed}")
            if len(rows) < batch_size:
                break

    print(f"\nDONE  processed={total_processed}  updated={total_updated}  "
          f"failed={total_failed}  dry_run={args.dry_run}",
          file=sys.stderr)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
