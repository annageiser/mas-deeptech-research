#!/usr/bin/env python3
"""Persist a hermes-agent cron run's output to Supabase.

Three modes:

    persist_signals.py --create-run
        Insert a new row into public.runs with system='hermes',
        status='running'. Print the new run's UUID to stdout (nothing else).

    persist_signals.py --close-run --run-id <uuid> --status ok|error
                         [--error-message <text>]
        Update the run row: finished_at=now(), status=<status>.

    persist_signals.py --actor-slug <slug> --stdin-file <path>
                         --run-id <uuid> [--run-log <path>]
        Parse the agent's stdout, validate signals against the four-signal
        taxonomy, upsert into public.signals tied to the given run_id.
        Print the count of NEW rows inserted to stdout (one int, no chatter)
        so the shell loop can sum it across actors.

Idempotency on (actor_slug, content_hash) is enforced by the table's unique
index. Misformatted or empty agent output silently produces 0 new signals
and exits 0 — that lets the shell loop carry on across the actor list.

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


# v0.4.20: embedding model matches systems/masfactory/.../embedding.py so
# cross-system signals about the same event embed to nearby points (required
# for cross-system semantic dedup). VENDORED — comparison-validity invariant
# says this persister cannot import from masfactory_system.
_EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"
_EMBEDDING_DIM = 768
_embedding_model: Any = None


def _embed_text(text: str) -> list[float] | None:
    """Return 768d BGE embedding or None if disabled / unavailable.

    Gated by HRM_EMBEDDINGS=1 env var (matches MASFactory's MASF_EMBEDDINGS).
    Lazy-loads fastembed on first call so cold start without embeddings is fast.
    """
    if os.environ.get("HRM_EMBEDDINGS", "").strip() not in ("1", "true", "yes"):
        return None
    if not text or not text.strip():
        return None
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding  # heavy native import; lazy
        except ImportError:
            return None
        try:
            _embedding_model = TextEmbedding(model_name=_EMBEDDING_MODEL_NAME)
        except Exception:
            return None
    try:
        gen = _embedding_model.embed([text.strip()])
        # v0.4.20: fastembed returns numpy float32 arrays which httpx's
        # JSON encoder rejects ("Object of type float32 is not JSON
        # serializable"). Convert element-wise to native Python float.
        vec = [float(x) for x in next(gen)]
        return vec if len(vec) == _EMBEDDING_DIM else None
    except Exception:
        return None


def _compose_signal_text(signal: dict[str, Any]) -> str:
    """SAME composition as systems/masfactory/.../embedding.py compose_signal_text.

    Concatenates title + evidence_quote + summary + dimension marker.
    """
    parts = [
        signal.get("title") or "",
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
        f"dimension:{signal.get('dimension') or 'unknown'}",
    ]
    return "\n".join(p.strip() for p in parts if p.strip())


# v0.4.24 — VENDORED VADER sentiment (matches systems/masfactory/.../sentiment.py).
# Both systems use IDENTICAL thresholds + composition so cross-system sentiment
# comparison isn't confounded by tooling differences. Default ON; disable with
# HRM_SENTIMENT=0|false|no|off. Reads HRM_SENTIMENT (not MASF_) so the two
# systems can be toggled independently if needed.
_VADER_POS_THRESHOLD = 0.05
_VADER_NEG_THRESHOLD = -0.05
_sentiment_analyzer: Any = None


def _sentiment_enabled() -> bool:
    return os.environ.get("HRM_SENTIMENT", "").strip().lower() not in (
        "0", "false", "no", "off"
    )


def _compose_sentiment_text(signal: dict[str, Any]) -> str:
    """SAME composition as MASFactory's sentiment.compose_sentiment_text."""
    parts = [signal.get("evidence_quote") or "", signal.get("summary") or ""]
    return " ".join(p.strip() for p in parts if p.strip())


def _sentiment_label(score: float) -> str:
    if score >= _VADER_POS_THRESHOLD:
        return "positive"
    if score <= _VADER_NEG_THRESHOLD:
        return "negative"
    return "neutral"


def _score_sentiment(signal: dict[str, Any]) -> tuple[float, str] | None:
    """Return (compound_score, label) or None when disabled / analyzer absent."""
    if not _sentiment_enabled():
        return None
    text = _compose_sentiment_text(signal)
    if not text:
        return None
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        except ImportError:
            return None
        try:
            _sentiment_analyzer = SentimentIntensityAnalyzer()
        except Exception:
            return None
    try:
        scores = _sentiment_analyzer.polarity_scores(text)
        compound = round(float(scores.get("compound", 0.0)), 4)
        return compound, _sentiment_label(compound)
    except Exception:
        return None


# v0.4.19: signal_type is now the Ehrenthal FOUR only. Defense is two
# boolean flags layered on top — see docs/migrations.md § v0.4.19.
VALID_SIGNAL_TYPES = {
    "legitimacy",
    "customer_cocreation",
    "community_ecosystem",
    "future_trajectory",
}


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Find the agent's signal-list JSON object in stdout.

    Strategy:
      1. Prefer a fenced ```json ... ``` block (the skill instructs this
         format, but Hermes's UI sometimes strips backticks when rendering
         in box mode).
      2. Fall back to scanning EVERY balanced top-level `{...}` block
         and returning the LARGEST one that contains a `signals` key.
         This handles both:
           - the agent emitting just an inner signal object (small wrong)
           - the rendered Hermes box stripping fence markers (no ```json)

    Returns None if no parseable signal-list object is found.
    """
    # Strategy 1: fenced block. Match non-greedy on the LAST occurrence.
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for candidate in reversed(fences):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "signals" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    # Strategy 2: enumerate ALL balanced {...} blocks in `text`. Among
    # parseable ones with a "signals" key, return the LARGEST (the outer
    # wrapper rather than any individual signal object).
    candidates: list[dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        for j in range(i, n):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[i : j + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and "signals" in parsed:
                            candidates.append(parsed)
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
        else:
            i = n
    if candidates:
        # Largest = outermost wrapper (contains all the inner signals)
        return max(candidates, key=lambda d: len(d.get("signals") or []))
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


# D.3 keyword backstop — deterministic detection independent of the agent's
# judgment. The agent's flag setting wins when true; this only fires the flag
# when the agent left it false but explicit keywords appear in the text.
DEFENSE_ENGAGEMENT_KEYWORDS = (
    "darpa", "afcea", "nato", "department of defense", "dod ",
    "dual-use", "dual use", "itar", "ear ", "export-control",
    "export control", "national defense", "ministry of defence",
    "ministry of defense", "armasuisse", "armaforces",
    "us army", "us navy", "us air force", "us space force",
)
DEFENSE_AMBIVALENCE_KEYWORDS = (
    "national security",
    "classified",
    "we cannot disclose",
    "cannot share details",
    "due to security",
    "for security reasons",
    "export restrictions",
    "restricted disclosure",
)


def _detect_defense_flags(s: dict[str, Any]) -> tuple[bool, bool]:
    """Return (engagement, ambivalence) detected purely from keywords.

    Searches the signal's title + summary + evidence_quote (all lowercased).
    OR'd with the agent's flag values at row-build time.
    """
    text = " ".join(
        str(s.get(k) or "") for k in ("title", "summary", "evidence_quote")
    ).lower()
    engagement = any(kw in text for kw in DEFENSE_ENGAGEMENT_KEYWORDS)
    ambivalence = any(kw in text for kw in DEFENSE_AMBIVALENCE_KEYWORDS)
    return engagement, ambivalence


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


def _supabase_env() -> tuple[str, str]:
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (base and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        sys.exit(2)
    return base, key


def _headers(api_key: str, *, prefer: str = "return=representation") -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _create_run() -> str:
    """Insert a runs row with status='running'. Print UUID."""
    base, key = _supabase_env()
    row = {
        "system": "hermes",
        "status": "running",
        "config_snapshot": {
            "image": "mas-deeptech-research/hermes:0.2.1",
            "lookback_days": int(os.environ.get("HERMES_LOOKBACK_DAYS", "180")),
            "limit_actors": int(os.environ.get("HERMES_LIMIT_ACTORS", "0") or 0),
        },
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{base.rstrip('/')}/rest/v1/runs",
            headers=_headers(key),
            json=row,
        )
        resp.raise_for_status()
        data = resp.json()
    if not data or "id" not in data[0]:
        print("runs insert returned no id", file=sys.stderr)
        return ""
    print(data[0]["id"])
    return data[0]["id"]


def _close_run(*, run_id: str, status: str, error_message: str | None) -> None:
    """PATCH a runs row to finalise it."""
    if status not in ("ok", "error"):
        print(f"invalid status: {status}", file=sys.stderr)
        sys.exit(2)
    base, key = _supabase_env()
    patch = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_message:
        patch["error_message"] = error_message[:2000]
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{base.rstrip('/')}/rest/v1/runs?id=eq.{run_id}",
            headers=_headers(key, prefer="return=minimal"),
            json=patch,
        )
        resp.raise_for_status()


def _upsert_signals(
    *,
    base_url: str,
    api_key: str,
    actor_slug: str,
    run_id: str,
    signals: list[dict[str, Any]],
    log_path: Path | None,
) -> int:
    """POST signals to Supabase PostgREST. Returns count of NEW rows.

    Maps the agent's JSON shape to the canonical public.signals schema
    (see systems/masfactory/.../persistence/schema.sql). Required fields
    the agent does NOT provide get sensible defaults:
      - source_kind = 'news'   (hermes-agent web-research output)
      - is_technical = False   (agent-discovered signals default to non-technical)
    """
    rows = []
    for s in signals:
        err = _validate_signal(s)
        if err:
            _log(log_path, f"skip {s.get('title', '?')!r}: {err}")
            continue
        rows.append({
            "run_id": run_id,
            "actor_slug": actor_slug,
            "system": "hermes",
            "source_kind": "news",
            "source_url": s["source_url"],
            "title": s["title"][:500],
            "summary": (s.get("summary") or "")[:2000],
            "evidence_quote": (s.get("evidence_quote") or "")[:500],
            "dimension": s["dimension"],
            "signal_type": s["signal_type"],
            "stakeholder": s.get("stakeholder"),
            "is_technical": False,
            "confidence": float(s.get("confidence", 0.5)),
            "observed_at": s.get("published_at"),
            "content_hash": _content_hash(actor_slug, s),
            # v0.4.19: defense overlays on the Ehrenthal four. Both default
            # to false; the agent sets them true when evidence is explicit.
            # D.3 backstop: deterministic keyword detection OR-ed with the
            # agent's setting — so a keyword-explicit signal can never end
            # up unflagged if the agent missed it.
            "defense_engagement":
                bool(s.get("defense_engagement", False)) or _detect_defense_flags(s)[0],
            "defense_ambivalence":
                bool(s.get("defense_ambivalence", False)) or _detect_defense_flags(s)[1],
        })
        # v0.4.20: compute embedding using the SAME model + composition as
        # System A so cross-system semantic dedup works (M.1). No-op when
        # HRM_EMBEDDINGS is unset; lazy-loads fastembed on first call.
        emb = _embed_text(_compose_signal_text(s))
        if emb is not None:
            rows[-1]["embedding"] = emb
        # v0.4.24: VADER sentiment (cheap, no LLM tokens). Vendored helper
        # uses the SAME thresholds + composition as System A so cross-system
        # comparison isn't confounded. No-op when HRM_SENTIMENT=0 / vader
        # missing — column stays NULL.
        sent = _score_sentiment(s)
        if sent is not None:
            rows[-1]["sentiment_score"], rows[-1]["sentiment_label"] = sent
    if not rows:
        return 0

    url = f"{base_url.rstrip('/')}/rest/v1/signals?on_conflict=actor_slug,source_url,content_hash"
    headers = _headers(api_key, prefer="resolution=ignore-duplicates,return=representation")
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=rows)
            resp.raise_for_status()
            inserted = resp.json() or []
            return len(inserted)
    except httpx.HTTPStatusError as exc:
        _log(log_path, f"HTTP {exc.response.status_code}: {exc.response.text[:500]}")
        raise
    except Exception as exc:  # noqa: BLE001 — log everything, raise cleanly
        _log(log_path, f"upsert failed: {exc}")
        raise


def _cmd_persist(args: argparse.Namespace) -> int:
    log_path = Path(args.run_log) if args.run_log else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    stdin_path = Path(args.stdin_file)
    if not stdin_path.is_file():
        print(f"stdin file not found: {stdin_path}", file=sys.stderr)
        return 1

    text = stdin_path.read_text(encoding="utf-8", errors="replace")
    block = _extract_json_block(text)
    if block is None:
        _log(log_path, f"[{args.actor_slug}] no JSON block found in agent stdout")
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

    base, key = _supabase_env()
    try:
        new = _upsert_signals(
            base_url=base,
            api_key=key,
            actor_slug=args.actor_slug,
            run_id=args.run_id,
            signals=signals,
            log_path=log_path,
        )
    except Exception:
        return 1

    print(new)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-run", action="store_true",
                      help="Insert a new public.runs row, print its UUID, exit.")
    mode.add_argument("--close-run", action="store_true",
                      help="Update the public.runs row's status + finished_at.")
    mode.add_argument("--actor-slug", help="Per-actor persist mode (default).")

    parser.add_argument("--stdin-file", help="Path to agent stdout (persist mode)")
    parser.add_argument("--run-id", help="UUID of the public.runs row")
    parser.add_argument("--run-log", help="Append parse/persist diagnostics here")
    parser.add_argument("--status", choices=("ok", "error"),
                        help="Final status (close-run mode)")
    parser.add_argument("--error-message", help="Failure detail (close-run mode)")
    args = parser.parse_args(argv)

    if args.create_run:
        return 0 if _create_run() else 1

    if args.close_run:
        if not args.run_id or not args.status:
            print("--close-run requires --run-id and --status", file=sys.stderr)
            return 2
        _close_run(run_id=args.run_id, status=args.status,
                   error_message=args.error_message)
        return 0

    # Persist mode
    if not args.run_id or not args.stdin_file:
        print("persist mode requires --run-id and --stdin-file", file=sys.stderr)
        return 2
    return _cmd_persist(args)


if __name__ == "__main__":
    raise SystemExit(main())
