#!/usr/bin/env python3
"""Backfill VADER sentiment on existing signals (both systems).

Mirrors backfill_embeddings.py — same Hermes wrapper container (which has
vaderSentiment installed in the upstream venv as of v0.4.24). Reads
`public.signals` rows where `sentiment_label IS NULL`, computes the
VADER compound score on the SAME composition as the live persister
(evidence_quote + summary), and PATCH-updates the row via Supabase
REST.

Why this script lives under `systems/hermes/scripts/` rather than
masfactory/: keeping it adjacent to the existing backfill_embeddings.py
makes it a one-command run from the same container that's already wired
to do bulk Supabase patches. The composition + thresholds match
MASFactory's sentiment.py verbatim — there's no system-A-specific
behaviour to vendor.

Usage from the VPS:

    cd /opt/mas-deeptech-research
    docker compose build hermes        # only if vaderSentiment isn't in image yet
    docker compose run --rm \\
      --entrypoint python hermes \\
      /opt/swiss-quantum/scripts/backfill_sentiment.py --system hermes
    docker compose run --rm \\
      --entrypoint python hermes \\
      /opt/swiss-quantum/scripts/backfill_sentiment.py --system masfactory

Or both systems in one go (default: --system all):

    docker compose run --rm \\
      --entrypoint python hermes \\
      /opt/swiss-quantum/scripts/backfill_sentiment.py

Useful flags:
  --batch-size N    rows per Supabase round-trip (default 100; max 1000)
  --limit N         stop after N rows total (0 = no limit)
  --dry-run         compute scores without UPDATE (smoke)
  --sleep S         seconds to pause between rows (0 = none)

Idempotent: re-running after a partial completion just picks up where
it left off (the `sentiment_label IS NULL` filter narrows on each
batch).

No imports from masfactory_system — comparison-validity invariant.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import httpx


# VENDORED from systems/masfactory/.../sentiment.py — same thresholds,
# same composition. If you change one, change the other.
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
_analyzer: Any = None


def _label_for(score: float) -> str:
    if score >= POS_THRESHOLD:
        return "positive"
    if score <= NEG_THRESHOLD:
        return "negative"
    return "neutral"


def _compose_sentiment_text(signal: dict) -> str:
    parts = [signal.get("evidence_quote") or "", signal.get("summary") or ""]
    return " ".join(p.strip() for p in parts if p.strip())


def _score(signal: dict) -> tuple[float, str] | None:
    global _analyzer
    text = _compose_sentiment_text(signal)
    if not text:
        return None
    if _analyzer is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        except ImportError:
            print(
                "FATAL: vaderSentiment not installed — run inside the Hermes "
                "wrapper image (it has the dep). Local dev: "
                "`pip install vaderSentiment>=3.3.2`.",
                file=sys.stderr,
            )
            sys.exit(2)
        _analyzer = SentimentIntensityAnalyzer()
    try:
        scores = _analyzer.polarity_scores(text)
        compound = round(float(scores.get("compound", 0.0)), 4)
        return compound, _label_for(compound)
    except Exception as exc:
        print(f"  vader failed: {exc}", file=sys.stderr)
        return None


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


def _fetch_batch(client: httpx.Client, base: str, headers: dict,
                 batch_size: int, system_filter: str | None) -> list[dict]:
    """Fetch rows lacking a sentiment label.

    system_filter:
      - "hermes" or "masfactory" → eq.<system>
      - None → all systems
    """
    sys_clause = f"&system=eq.{system_filter}" if system_filter else ""
    url = (
        f"{base.rstrip('/')}/rest/v1/signals"
        f"?sentiment_label=is.null"
        f"{sys_clause}"
        f"&select=id,evidence_quote,summary"
        f"&limit={batch_size}&order=inserted_at.asc"
    )
    r = client.get(url, headers=headers)
    r.raise_for_status()
    return r.json() or []


def _update_one(client: httpx.Client, base: str, headers: dict,
                row_id: str, score: float, label: str) -> bool:
    url = f"{base.rstrip('/')}/rest/v1/signals?id=eq.{row_id}"
    body = {"sentiment_score": score, "sentiment_label": label}
    try:
        r = client.patch(
            url,
            headers={**headers, "Prefer": "return=minimal"},
            json=body,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        print(
            f"  PATCH {row_id}: HTTP {exc.response.status_code} "
            f"{exc.response.text[:200]}",
            file=sys.stderr,
        )
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Rows per fetch (default 100; max 1000)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after this many rows total (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute scores but skip UPDATE")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="Seconds to sleep between rows (default 0)")
    parser.add_argument("--system", default="all",
                        choices=["all", "hermes", "masfactory"],
                        help="Which system's rows to score (default all)")
    args = parser.parse_args(argv)

    if args.batch_size < 1 or args.batch_size > 1000:
        print("--batch-size must be 1..1000", file=sys.stderr)
        return 2

    base, key = _supabase_env()
    headers = _headers(key)
    system_filter = None if args.system == "all" else args.system

    total_processed = 0
    total_updated = 0
    total_failed = 0

    with httpx.Client(timeout=60.0) as client:
        while True:
            if args.limit and total_processed >= args.limit:
                break
            batch_size = (
                min(args.batch_size, args.limit - total_processed)
                if args.limit else args.batch_size
            )
            try:
                rows = _fetch_batch(client, base, headers, batch_size, system_filter)
            except httpx.HTTPStatusError as exc:
                print(
                    f"FATAL: fetch failed: HTTP {exc.response.status_code} "
                    f"{exc.response.text[:200]}",
                    file=sys.stderr,
                )
                return 1
            if not rows:
                break

            batch_updated = 0
            batch_failed = 0
            for row in rows:
                scored = _score(row)
                if scored is None:
                    # Empty text → label as 'neutral' with score 0 so the
                    # row stops matching `sentiment_label IS NULL` and we
                    # don't reprocess it on every re-run. (Backfill is
                    # idempotent only if every processed row leaves the
                    # filter set.)
                    score, label = 0.0, "neutral"
                else:
                    score, label = scored
                if args.dry_run:
                    batch_updated += 1
                    total_updated += 1
                else:
                    if _update_one(client, base, headers, row["id"], score, label):
                        batch_updated += 1
                        total_updated += 1
                    else:
                        batch_failed += 1
                        total_failed += 1
                total_processed += 1
                if args.sleep > 0:
                    time.sleep(args.sleep)
            print(
                f"batch: fetched={len(rows)} updated={batch_updated} "
                f"failed={batch_failed}  running total: processed={total_processed} "
                f"updated={total_updated} failed={total_failed}"
            )
            if len(rows) < batch_size:
                break

    print(
        f"\nDONE  processed={total_processed}  updated={total_updated}  "
        f"failed={total_failed}  dry_run={args.dry_run}",
        file=sys.stderr,
    )
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
