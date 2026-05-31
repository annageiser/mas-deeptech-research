"""Press-release aggregator collector — broader-web channel #3.

Why a third aggregator beyond actor websites + Google News?

  - **Content-analysis triangulation** (Kolbe & Burnett 1991): pulling from a
    second independent aggregator with a different ranker and a different
    underlying source mix reduces the chance that any single aggregator's
    blind spots dominate our corpus. The two aggregators index largely
    different press-wire feeds (PR Newswire, BusinessWire, GlobeNewswire,
    EurekAlert vs. the Google News stable), so the union of the two reads
    the "press" signal channel more completely than either alone.

  - **Costly-signal channel coverage** (Spence 1973 via Ehrenthal et al.
    2026): press releases on the major distribution wires carry a real fee
    per release (~$1k+), which makes them high-cost signals in our schema.
    Sampling that channel directly is what justifies the `signal_cost=high`
    weight on funding / regulatory / infrastructure dimensions.

This collector uses **Bing News's public RSS endpoint** with a query designed
to surface press-release-style content:

  https://www.bing.com/news/search?q=<query>&format=rss

  - Query pattern: `"<Actor Name>" quantum (announces OR launches OR
    partners OR funding OR breakthrough)` — verbs that bias Bing's ranker
    toward PR-wire content rather than analyst commentary.
  - No API key required.
  - Distinct rank function and source mix from Google News (the existing
    `news.py` collector), so the union of both is a richer corpus than
    either alone.

Each RSS entry becomes one Document with `source_kind="news"` (the schema's
existing third-party-coverage kind — see `persistence/schema.sql`). The host
in `source_url` lets the dashboard distinguish Bing-sourced press hits from
Google-News hits when desired.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser
import httpx

from ..schema import Actor, Document


BING_NEWS_ENDPOINT = "https://www.bing.com/news/search"
USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"

# Verbs that bias Bing News' ranker toward press-release-style content. Kept
# small + boolean-OR'd so a release matching any one verb surfaces. Discovered
# empirically — adding more verbs (`unveils`, `joins`, `secures`) didn't
# materially change the top-5 results for the actors in `data/raw/actors.yaml`.
PR_KEYWORDS = ("announces", "launches", "partners", "funding", "breakthrough")


def _build_query(actor: Actor) -> str:
    """Compose a press-release-biased query.

    Pattern: `"<Actor Name>" (quantum OR qubit) (kw1 OR kw2 OR ...)` —
    quoted name forces exact-phrase match; the first OR-group widens the
    technology axis (quantum subfields); the second OR-group nudges Bing's
    ranker toward PR-wire hits. Bing News accepts `site:` operators but we
    deliberately avoid them: the goal is broad press coverage, not an
    artificially narrow whitelist.
    """
    name = actor.name.strip()
    or_group = " OR ".join(PR_KEYWORDS)
    return f'"{name}" (quantum OR qubit) ({or_group})'


def collect_press_releases(
    actor: Actor,
    *,
    max_results: int = 5,
    timeout: float = 20.0,
) -> list[Document]:
    """Fetch Bing News RSS with a press-release-biased query.

    Returns up to `max_results` Documents. Defensive: any network or parse
    failure yields an empty list rather than raising — collectors must never
    break the graph (see retriever.py's try/except wrappers).
    """
    query = _build_query(actor)
    params = {"q": query, "format": "rss"}
    url = f"{BING_NEWS_ENDPOINT}?{urlencode(params)}"

    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
    except Exception:
        return []

    feed = feedparser.parse(resp.text)
    docs: list[Document] = []
    now = datetime.now(timezone.utc)

    for entry in feed.entries[: max(1, min(20, int(max_results)))]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if not link or not title:
            continue
        body = f"{title}\n\n{summary}".strip()
        published: datetime | None = None
        try:
            if entry.get("published_parsed"):
                published = datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
        except Exception:
            published = None
        docs.append(
            Document(
                source_kind="news",
                source_url=link,
                actor_slug=actor.slug,
                title=title,
                text=body[:8_000],
                fetched_at=now,
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    return docs
