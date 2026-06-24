"""Read-only access to the editorial training layer (v0.4.37).

Both producer systems consume two new tables Anna manages through the
dashboard CRUD:

  - public.manual_signals  → few-shot examples for the Classifier prompt
                             AND a `recommended_urls` list per actor for
                             the Retriever to also pick up.
  - public.signal_sources  → RSS / Atom / URL sources the Retriever
                             fetches in addition to data/raw/rss_feeds.yaml.
                             Honors crawl_frequency_hours as a floor
                             (skip if last_fetched_at is too recent).

VENDORED — there is a structurally-identical sibling at
systems/hermes/scripts/training_layer.py. No cross-imports between
systems (comparison-validity invariant). If you edit either side, edit
both.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class ManualExample:
    """A hand-curated signal Anna added through /labels."""

    id: str
    source_url: str
    title: Optional[str]
    notes: Optional[str]
    labels: list[str]
    signal_type: Optional[str]
    dimension: Optional[str]
    actor_slugs: list[str]


@dataclass(frozen=True)
class SourceEntry:
    """A managed RSS / Atom / URL source from /sources."""

    id: str
    url: str
    kind: str  # 'rss' | 'atom' | 'url'
    label: Optional[str]
    labels: list[str]
    actor_slugs: list[str]
    enabled: bool
    crawl_frequency_hours: int
    last_fetched_at: Optional[datetime]


@dataclass
class TrainingLayer:
    """Snapshot of manual signals + sources, fetched once per run.

    Both systems pull this at run-start. The data is fetched via plain
    httpx against Supabase PostgREST (same pattern as Hermes's persister),
    deliberately not via the masfactory `supabase` client so this helper
    is import-safe from anywhere in the package.
    """

    manual: list[ManualExample] = field(default_factory=list)
    sources: list[SourceEntry] = field(default_factory=list)

    # --------------- lookups used at runtime ---------------

    def few_shot_for_actor(self, actor_slug: str, *, max_examples: int = 8) -> list[ManualExample]:
        """Examples relevant to a specific actor + a small global pool.

        Returns at most `max_examples`. Actor-specific examples win
        ordering; global ones fill the remainder so the Classifier sees
        a diverse mix even for actors with no curated examples yet.
        """
        actor_specific = [m for m in self.manual if actor_slug in m.actor_slugs]
        global_pool = [m for m in self.manual if not m.actor_slugs]
        out: list[ManualExample] = []
        out.extend(actor_specific[:max_examples])
        if len(out) < max_examples:
            out.extend(global_pool[: max_examples - len(out)])
        return out

    def recommended_urls_for_actor(self, actor_slug: str) -> list[str]:
        """URLs from manual signals related to this actor — Retriever
        should pick them up directly even when they're not in any RSS feed.
        """
        return [m.source_url for m in self.manual if actor_slug in m.actor_slugs]

    def sources_due(self, *, actor_slug: Optional[str] = None) -> list[SourceEntry]:
        """Enabled sources whose crawl_frequency_hours floor has elapsed.

        If actor_slug is given, also includes sources scoped to that
        actor (sources with empty actor_slugs apply to ALL actors).
        """
        now = datetime.now(timezone.utc)
        out: list[SourceEntry] = []
        for s in self.sources:
            if not s.enabled:
                continue
            if actor_slug is not None and s.actor_slugs and actor_slug not in s.actor_slugs:
                continue
            if s.last_fetched_at is not None and s.crawl_frequency_hours > 0:
                floor = s.last_fetched_at + timedelta(hours=s.crawl_frequency_hours)
                if floor > now:
                    continue
            out.append(s)
        return out


# ---------------- fetcher ----------------


_DEFAULT_TIMEOUT_S = 15.0


def _supabase_env() -> Optional[tuple[str, str]]:
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (base and key):
        return None
    return base.rstrip("/"), key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        # PostgREST returns ISO-8601; Python's fromisoformat handles
        # most variants but not the trailing 'Z' on some Supabase rows.
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def load_training_layer(*, timeout_s: float = _DEFAULT_TIMEOUT_S) -> TrainingLayer:
    """Best-effort fetch. Returns an empty TrainingLayer on any error
    so the cron never breaks because the editorial layer is unreachable.
    """
    env = _supabase_env()
    if env is None:
        return TrainingLayer()
    base, key = env
    headers = _headers(key)
    try:
        with httpx.Client(timeout=timeout_s) as client:
            manual_resp = client.get(
                f"{base}/rest/v1/manual_signals",
                params={"select": "*", "order": "updated_at.desc", "limit": "500"},
                headers=headers,
            )
            sources_resp = client.get(
                f"{base}/rest/v1/signal_sources",
                params={"select": "*", "enabled": "eq.true", "limit": "500"},
                headers=headers,
            )
        manual_rows = manual_resp.json() if manual_resp.is_success else []
        sources_rows = sources_resp.json() if sources_resp.is_success else []
    except Exception:
        return TrainingLayer()

    manual: list[ManualExample] = []
    for r in manual_rows or []:
        try:
            manual.append(
                ManualExample(
                    id=r["id"],
                    source_url=r["source_url"],
                    title=r.get("title"),
                    notes=r.get("notes"),
                    labels=list(r.get("labels") or []),
                    signal_type=r.get("signal_type"),
                    dimension=r.get("dimension"),
                    actor_slugs=list(r.get("actor_slugs") or []),
                )
            )
        except Exception:
            continue

    sources: list[SourceEntry] = []
    for r in sources_rows or []:
        try:
            sources.append(
                SourceEntry(
                    id=r["id"],
                    url=r["url"],
                    kind=r["kind"],
                    label=r.get("label"),
                    labels=list(r.get("labels") or []),
                    actor_slugs=list(r.get("actor_slugs") or []),
                    enabled=bool(r.get("enabled", True)),
                    crawl_frequency_hours=int(r.get("crawl_frequency_hours") or 24),
                    last_fetched_at=_parse_dt(r.get("last_fetched_at")),
                )
            )
        except Exception:
            continue

    return TrainingLayer(manual=manual, sources=sources)


def mark_source_fetched(
    source_id: str,
    *,
    status: str,
    item_count: int = 0,
    error: Optional[str] = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> None:
    """Patch a source's last-fetched bookkeeping after a producer fetch.

    Mirrors api_app.training.mark_source_fetched but uses PostgREST
    directly so the producer container doesn't need to import the API
    package.
    """
    env = _supabase_env()
    if env is None:
        return
    base, key = env
    payload = {
        "last_fetched_at": datetime.now(timezone.utc).isoformat(),
        "last_status": status,
        "last_error": (error or "")[:2000] or None,
        "last_item_count": int(item_count),
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            client.patch(
                f"{base}/rest/v1/signal_sources",
                params={"id": f"eq.{source_id}"},
                headers={**_headers(key), "Prefer": "return=minimal"},
                json=payload,
            )
    except Exception:
        # Best-effort — never break a cron because bookkeeping failed.
        return
