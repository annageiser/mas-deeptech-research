"""RSS-feed collector — feed-first rather than actor-first.

The four existing collectors (arxiv, website, news, press, patents) are
*actor-first*: for each actor, fetch documents matching that actor. This
collector inverts that: fetch every configured feed, then surface entries
to the actor(s) whose name (or alias) matches the entry text.

Why feed-first matters:
  - General-quantum feeds (The Quantum Insider Daily, Phys.org Quantum)
    publish entries that touch multiple actors at once — collecting once
    per feed and broadcasting to matching actors is much cheaper than
    re-fetching the feed once per actor.
  - The same feed cache feeds both MAS systems (config in
    data/raw/rss_feeds.yaml is read by both — comparative-validity
    invariant preserved).

Feed groups (from rss_feeds.yaml):
  - industry   : surfaced to ANY actor whose name/alias matches the entry
  - swiss_media: same logic, Swiss-domestic source pool
  - vendor     : pre-attributed to one specific actor_slug
  - defense    : same as industry but tag-distinct for the v0.4.2
                 defense_signals classification

Defensive: any feed failure (network, parse, robots-block) drops just
that feed; the rest of the scrape continues.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import httpx
import yaml

from ..schema import Actor, Document

log = logging.getLogger(__name__)


USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"


def _config_path() -> Path:
    """Locate rss_feeds.yaml. Env override > repo data/raw > package default."""
    env = os.environ.get("MASF_RSS_FEEDS_PATH")
    if env and os.path.isfile(env):
        return Path(env)
    # Repo bind-mount path inside the container
    container = Path("/data/raw/rss_feeds.yaml")
    if container.is_file():
        return container
    # Dev-time fallback walking up from this file
    p = Path(__file__).resolve()
    for _ in range(6):
        candidate = p.parent / "data" / "raw" / "rss_feeds.yaml"
        if candidate.is_file():
            return candidate
        p = p.parent
    raise FileNotFoundError("rss_feeds.yaml not found — set MASF_RSS_FEEDS_PATH")


def load_feed_config() -> dict[str, list[dict]]:
    """Return {group: [feed_dict, ...]} for industry / swiss_media / vendor / defense."""
    try:
        with open(_config_path(), "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        log.warning("rss_feeds.yaml not found; RSS collector returns nothing.")
        return {}


def _fetch_feed(url: str, *, timeout: float = 20.0) -> Optional[str]:
    """Return the raw feed body or None on any error."""
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        log.warning("RSS fetch failed for %s: %s", url, exc)
        return None


def _actor_needles(actor: Actor) -> list[str]:
    out: list[str] = []
    for n in [actor.name] + list(actor.aliases or []):
        n = (n or "").strip().lower()
        if n and len(n) >= 3:  # avoid 2-letter matches like "IQ"
            out.append(n)
    return out


def _matches_actor(needles: list[str], blob: str) -> bool:
    if not blob or not needles:
        return False
    lo = blob.lower()
    return any(n in lo for n in needles)


def _entry_to_document(entry, *, actor: Actor, feed_name: str) -> Optional[Document]:
    link = (entry.get("link") or "").strip()
    title = (entry.get("title") or "").strip()
    summary = (entry.get("summary") or entry.get("description") or "").strip()
    if not link or not title:
        return None
    body = f"[{feed_name}] {title}\n\n{summary}".strip()
    return Document(
        source_kind="news",
        source_url=link,
        actor_slug=actor.slug,
        title=title,
        text=body[:8_000],
        fetched_at=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def collect_rss_for_actors(
    actors: list[Actor],
    *,
    max_entries_per_feed: int = 25,
) -> dict[str, list[Document]]:
    """Pull all configured feeds once; broadcast matching entries to actors.

    Returns {actor_slug: [Document, ...]} for every actor that picked up
    at least one entry. Actors with zero matches are omitted from the
    result dict.

    Side-effect (v0.4.3): unmatched industry/swiss_media/defense entries
    are persisted to public.industry_news for the worldwide-quantum-news
    page. See collect_industry_news_unattributed() for the standalone
    entrypoint used when no actor pool is available.
    """
    cfg = load_feed_config()
    if not cfg or not actors:
        return {}

    actor_by_slug = {a.slug: a for a in actors}
    actor_needles = {a.slug: _actor_needles(a) for a in actors}

    out: dict[str, list[Document]] = {a.slug: [] for a in actors}

    # vendor feeds: pre-attributed to a specific actor
    for feed in cfg.get("vendor", []) or []:
        slug = feed.get("actor_slug")
        if not slug or slug not in actor_by_slug:
            continue
        body = _fetch_feed(feed["url"])
        if not body:
            continue
        parsed = feedparser.parse(body)
        for entry in parsed.entries[: max_entries_per_feed]:
            doc = _entry_to_document(entry, actor=actor_by_slug[slug], feed_name=feed["name"])
            if doc:
                out[slug].append(doc)

    # industry / swiss_media / defense: match entries against all actors
    for group in ("industry", "swiss_media", "defense"):
        for feed in cfg.get(group, []) or []:
            body = _fetch_feed(feed["url"])
            if not body:
                continue
            parsed = feedparser.parse(body)
            for entry in parsed.entries[: max_entries_per_feed]:
                title = entry.get("title") or ""
                summary = entry.get("summary") or entry.get("description") or ""
                blob = f"{title}\n{summary}"
                for slug, needles in actor_needles.items():
                    if _matches_actor(needles, blob):
                        doc = _entry_to_document(
                            entry, actor=actor_by_slug[slug], feed_name=feed["name"]
                        )
                        if doc:
                            out[slug].append(doc)

    # Drop empty actor entries for a cleaner audit folder.
    return {slug: docs for slug, docs in out.items() if docs}


def collect_industry_news_unattributed(
    *,
    max_entries_per_feed: int = 50,
) -> list[dict]:
    """v0.4.3 — fetch industry/swiss_media/defense feeds and return EVERY
    entry as an industry_news record (not actor-attributed). Used by a
    separate cron job that populates public.industry_news.

    Each record: source_url, source_name, title, summary, published_at,
    content_hash. Caller upserts on (source_url, content_hash) for idempotence.
    """
    import hashlib
    cfg = load_feed_config()
    if not cfg:
        return []
    records: list[dict] = []
    for group in ("industry", "swiss_media", "defense"):
        for feed in cfg.get(group, []) or []:
            body = _fetch_feed(feed["url"])
            if not body:
                continue
            parsed = feedparser.parse(body)
            for entry in parsed.entries[: max_entries_per_feed]:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                url = (entry.get("link") or "").strip()
                if not title or not url:
                    continue
                published = None
                try:
                    if entry.get("published_parsed"):
                        published = datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
                except Exception:
                    published = None
                body_blob = f"{title}\n\n{summary}"
                records.append({
                    "source_url": url,
                    "source_name": feed["name"],
                    "title": title[:500],
                    "summary": summary[:2000],
                    "published_at": published.isoformat() if published else None,
                    "content_hash": hashlib.sha256(body_blob.encode("utf-8")).hexdigest(),
                })
    return records
