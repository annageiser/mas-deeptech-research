"""arXiv collector — uses the public Atom export, no auth required.

We deliberately use the documented `http://export.arxiv.org/api/query` endpoint
(returns Atom XML). Each entry becomes one Document for the Extractor.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser
import httpx

from ..schema import Actor, Document


ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"


def collect_arxiv(actor: Actor, *, max_results: int = 5, timeout: float = 30.0) -> list[Document]:
    """Return up to `max_results` recent arXiv entries for an actor.

    `actor.arxiv_query` is used directly; falls back to the actor's name if not
    set. The query is wrapped to limit results and sort by submission date.
    """
    query = (actor.arxiv_query or actor.name).strip()
    if not query:
        return []

    params = urlencode(
        {
            "search_query": f"all:{query}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
    )
    url = f"{ARXIV_ENDPOINT}?{params}"

    with httpx.Client(timeout=timeout, headers={"User-Agent": "masfactory-thesis/0.1 (research)"}) as client:
        resp = client.get(url)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    documents: list[Document] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        link = entry.get("link") or ""
        if not title or not summary:
            continue
        body = f"{title}\n\n{summary}"
        documents.append(
            Document(
                source_kind="arxiv",
                source_url=link,
                actor_slug=actor.slug,
                title=title,
                text=body,
                fetched_at=datetime.now(timezone.utc),
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    return documents
