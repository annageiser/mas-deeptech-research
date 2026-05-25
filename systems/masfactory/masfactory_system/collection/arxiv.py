"""arXiv collector — uses the public Atom export, no auth required.

We deliberately use the documented `https://export.arxiv.org/api/query`
endpoint (returns Atom XML). Each entry becomes one Document for the
Extractor.

Throttling: arXiv's terms of use ask for at most 1 request every 3 seconds.
The per-actor Loop in System A hits this collector once per actor in fast
succession, so we keep a module-level "last call" timestamp and sleep just
enough between requests to stay under the limit.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser
import httpx

from ..schema import Actor, Document


_ARXIV_MIN_INTERVAL = 3.1  # seconds — arXiv asks for ≥3s between requests
_last_call_at = 0.0
_throttle_lock = threading.Lock()


def _throttle() -> None:
    """Sleep just enough since the previous arXiv request."""
    global _last_call_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < _ARXIV_MIN_INTERVAL:
            time.sleep(_ARXIV_MIN_INTERVAL - elapsed)
        _last_call_at = time.monotonic()


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"

# arXiv field prefixes — if the caller-provided query already starts with one
# of these, we use it verbatim (no `all:` wrap). Otherwise we wrap as `all:`
# so a bare actor name still searches across all metadata.
# Ref: https://info.arxiv.org/help/api/user-manual.html#query_details
_ARXIV_FIELD_PREFIXES = ("ti:", "au:", "abs:", "co:", "jr:", "cat:", "rn:", "id:", "all:", "aff:")


def _normalise_arxiv_query(raw: str) -> str:
    """Pass through `aff:` / `au:` etc. unchanged; wrap bare text as `all:`.

    Several actor records use `aff:"ETH Zurich" AND (qubit OR quantum)` to
    bias toward affiliation matches. Wrapping that in `all:` would break the
    field operator; the older collector did exactly that, which silently
    weakened affiliation filtering for ~half the actors.
    """
    s = raw.strip()
    if not s:
        return ""
    lo = s.lower()
    if any(lo.startswith(p) for p in _ARXIV_FIELD_PREFIXES):
        return s
    return f"all:{s}"


def collect_arxiv(actor: Actor, *, max_results: int = 5, timeout: float = 30.0) -> list[Document]:
    """Return up to `max_results` recent arXiv entries for an actor.

    `actor.arxiv_query` is used directly when it starts with an arXiv field
    operator (`aff:`, `au:`, `ti:`, etc.); otherwise it's wrapped as
    `all:<query>`. Falls back to the actor's name if `arxiv_query` is empty.
    """
    query = _normalise_arxiv_query(actor.arxiv_query or actor.name)
    if not query:
        return []

    params = urlencode(
        {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
    )
    url = f"{ARXIV_ENDPOINT}?{params}"

    # arXiv now serves https; the http endpoint returns 301. Follow redirects
    # so we don't lose every actor's papers to the http→https hop.
    _throttle()
    with httpx.Client(
        timeout=timeout,
        headers={"User-Agent": "masfactory-thesis/0.1 (research)"},
        follow_redirects=True,
    ) as client:
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
