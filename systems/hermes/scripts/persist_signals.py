#!/usr/bin/env python3
"""Parse a single hermes agent run's stdout and upsert signals to Supabase.

The agent's stdout (per the collect-swiss-quantum-signals skill) ends
with a single JSON code block of the form:

    {"actor_slug": "...", "collected_at": "...", "signals": [...]}

This script:
  1. Reads stdout, extracts the LAST ```json ... ``` block, or falls back
     to the last brace-balanced JSON object in the output.
  2. Validates the four-signal taxonomy + per-signal required fields.
  3. Upserts each accepted signal into public.signals with
     system='hermes', honouring (actor_slug, content_hash)
     idempotency via the existing unique index.
  4. Prints the number of NEW rows inserted to stdout (one int, no chatter)
     so the shell loop can sum it across actors. Errors go to stderr +
     the --run-log file and exit non-zero.

No imports from masfactory_system or hermes_system — comparison-validity
invariant. We use httpx directly against Supabase's PostgREST endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


# Accepted signal_type values (Ehrenthal four + thesis-novel defense).
VALID_SIGNAL_TYPES = {
    "legitimacy",
    "customer_cocreation",
    "community_ecosystem",
    "future_trajectory",
    "defense_signals",
}


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Find the last well-formed JSON object in agent stdout.

    Strategy:
      1. Prefer a fenced ```json ... ``` block (skill instructs this).
      2. Fall back to a brace-balanced scan from the rightmost `{`.
    Returns None if no parseable object is found.
    """
    # Strategy 1: fenced block. Match non-greedy on the LAST occurrence.
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for candidate in reversed(fences):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Strategy 2: brace-balanced scan from the end. Stop at the first
    # balanced object that parses.
    last_open = text.rfind("{")
    while last_open != -1:
        depth = 0
        for i, ch in enumerate(text[last_open:], start=last_open):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[last_open : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        last_open = text.rfind("{", 0, last_open)
    return None


def _content_hash(actor_slug: str, signal: dict[str, Any]) -> str:
    """Stable hash so duplicate runs don't insert duplicate signals.

    Uses (actor_slug, source_url, title) — covers both the case where
    the same URL is found twice AND where two different URLs report
    the same event under the same title."""
    blob = "|".join([
        actor_slug,
        (signal.get("source_url") or "").strip().lower(),
        (signal.get("title") or "").strip().lower(),
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_signal(s: dict[str, Any]) -> str | None:
    """Return None if signal is valid; otherwise a short error message."""
    for required in ("title", "source_url", "signal_type", "dimension"):
        if not s.get(required):
            return f"missing required field: {required}"
    if s["signal_type"] not in VALID_SIGNAL_TYPES:
        return f"invalid signal_type: {s['signal_type']!r}"
    if not isinstance(s.get("confidence", 0), (int, float)):
        return "confidence must be numeric"
    return None


def _log(path: Path | None, msg: str) -> None:
    if path:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(msg + "\n")


def _upsert_signals(
    *,
    base_url: str,
    api_key: str,
    actor_slug: str,
    signals: list[dict[str, Any]],
    log_path: Path | None,
) -> int:
    """POST signals to Supabase PostgREST. Returns count of NEW rows."""
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # `merge-duplicates` upserts on the conflict target; ignore-duplicates
        # would skip silently and not return the new rows, so we use merge
        # with `Prefer: return=representation` to count new vs updated.
        "Prefer": "resolution=ignore-duplicates,return=representation",
    }
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for s in signals:
        err = _validate_signal(s)
        if err:
            _log(log_path, f"skip {s.get('title', '?')!r}: {err}")
            continue
        rows.append({
            "actor_slug": actor_slug,
            "system": "hermes",
            "signal_type": s["signal_type"],
            "dimension": s["dimension"],
            "stakeholder": s.get("stakeholder"),
            "title": s["title"][:500],
            "summary": (s.get("summary") or "")[:2000],
            "evidence_quote": (s.get("evidence_quote") or "")[:500],
            "source_url": s["source_url"],
            "source_name": s.get("source_name"),
            "published_at": s.get("published_at"),
            "confidence": float(s.get("confidence", 0.5)),
            "content_hash": _content_hash(actor_slug, s),
            "collected_at": now,
        })
    if not rows:
        return 0

    url = f"{base_url.rstrip('/')}/rest/v1/signals?on_conflict=actor_slug,content_hash"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=rows)
            resp.raise_for_status()
            inserted = resp.json() or []
            return len(inserted)
    except httpx.HTTPStatusError as exc:
        _log(log_path, f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
        raise
    except Exception as exc:  # noqa: BLE001 — log everything, raise cleanly
        _log(log_path, f"upsert failed: {exc}")
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-slug", required=True, help="Slug from actors.yaml")
    parser.add_argument("--stdin-file", required=True, help="Path to agent stdout")
    parser.add_argument("--run-log", help="Append parse/persist diagnostics here")
    args = parser.parse_args(argv)

    log_path = Path(args.run_log) if args.run_log else None
    log_path and log_path.parent.mkdir(parents=True, exist_ok=True)

    stdin_path = Path(args.stdin_file)
    if not stdin_path.is_file():
        print(f"stdin file not found: {stdin_path}", file=sys.stderr)
        return 1

    text = stdin_path.read_text(encoding="utf-8", errors="replace")
    block = _extract_json_block(text)
    if block is None:
        _log(log_path, f"[{args.actor_slug}] no JSON block found in agent stdout")
        # Don't fail — just zero signals. Many actors legitimately have nothing.
        print("0")
        return 0

    if block.get("actor_slug") and block["actor_slug"] != args.actor_slug:
        _log(
            log_path,
            f"[{args.actor_slug}] WARN: agent returned actor_slug="
            f"{block['actor_slug']!r}, using --actor-slug instead",
        )
    signals = block.get("signals") or []
    if not isinstance(signals, list):
        _log(log_path, f"[{args.actor_slug}] signals is not a list — got {type(signals).__name__}")
        print("0")
        return 0

    base_url = os.environ.get("SUPABASE_URL", "").strip()
    api_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (base_url and api_key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        return 2

    try:
        new = _upsert_signals(
            base_url=base_url,
            api_key=api_key,
            actor_slug=args.actor_slug,
            signals=signals,
            log_path=log_path,
        )
    except Exception:
        # Diagnostics already logged. Surface non-zero to the shell loop.
        return 1

    print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
