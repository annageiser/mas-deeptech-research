"""Google News RSS collector.

Academic justification for broadening beyond actor-controlled sources:
Kolbe & Burnett (1991) on content-analysis methodology — third-party
coverage is a less self-serving signal than what an actor publishes about
itself, and aggregating both yields a more balanced legitimacy reading
(Suchman 1995 strategic vs cognitive legitimacy; Song et al. 2025 on
coattail effects via partner / customer coverage).

We use Google News's public RSS endpoint:
    https://news.google.com/rss/search?q=<query>&hl=en&gl=CH&ceid=CH:en
- `q` — search query (we use actor name + "quantum" + Switzerland)
- `hl` — interface language (en)
- `gl` — geolocation bias (CH for Switzerland)
- `ceid` — country + language for the results bundle

Each RSS entry becomes one Document with the news article's URL,
publication date, and a short title+description as text.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser
import httpx

from ..schema import Actor, Document


GNEWS_ENDPOINT = "https://news.google.com/rss/search"
USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"


def _build_query(actor: Actor) -> str:
    """Compose the search query.

    Pattern: `"<Actor Name>" (quantum OR qubit OR QKD)` — quoted name forces
    an exact-phrase match. The keyword OR-group widens the technology axis
    so we catch quantum-subfield coverage (computing / sensing / key
    distribution / metrology) that "quantum" alone may miss — Ehrenthal et
    al. 2026's vendor-comms corpus explicitly covers these sub-fields.

    `gl=CH` (geolocation bias) at the endpoint biases toward Switzerland;
    an in-query Switzerland-OR-filter was too restrictive in v0 (returned
    0 results for actors whose press doesn't repeat the country name in
    headlines). The Critic now filters hard for actor + quantum relevance
    so a wider funnel doesn't degrade the final corpus.
    """
    name = actor.name.strip()
    return f'"{name}" (quantum OR qubit OR QKD)'


def collect_google_news(
    actor: Actor,
    *,
    max_results: int = 5,
    timeout: float = 20.0,
) -> list[Document]:
    """Fetch Google News RSS for the actor and return Documents per article."""
    query = _build_query(actor)
    params = {"q": query, "hl": "en", "gl": "CH", "ceid": "CH:en"}
    url = f"{GNEWS_ENDPOINT}?{urlencode(params)}"

    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception:
        return []

    feed = feedparser.parse(resp.text)
    docs: list[Document] = []
    now = datetime.now(timezone.utc)

    for entry in feed.entries[:max_results]:
        # Google News rewrites article URLs through news.google.com/articles/...
        # — that's fine, both the redirect target and the original work for
        # the source_url field (the dashboard's link still opens the article).
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if not link or not title:
            continue
        body = f"{title}\n\n{summary}".strip()
        # Try to capture the publication date when available
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
