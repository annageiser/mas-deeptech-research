"""SearXNG web-search collector (v0.5.0).

Broad open-web discovery via the shared self-hosted SearXNG instance — the
SAME substrate System B (hermes) queries — so the A-vs-B comparison isolates
architecture (Modular-RAG graph vs agentic loop), not search source. See
docs/iterations/v0.5.0-reference-architecture-retrieval.md.

Why this matters for recall: the Google-News collector (`news.py`) is
Switzerland-geo-biased (`gl=CH`), which suppresses coverage of GLOBAL actors
that operate in Switzerland (e.g. IBM Research Zurich — 12 signals, 100 %
homepage-scrape, zero news — while System B's broad search found 33 incl. 10
news). This collector is deliberately NOT geo-biased: it queries the actor
name + the quantum technology axis and lets the Critic filter for
Swiss-quantum relevance (the codebase's "wide funnel + strict Critic"
principle — see news.py).

Each SearXNG result (title + snippet + url) becomes one Document with
`source_kind="news"` (third-party web coverage; the schema's SourceKind has no
dedicated web-search kind and reusing "news" avoids a schema/DB migration).
Snippet-level evidence — the Extractor / Critic still see the title + snippet
and can accept or reject. Full-text fetch of result URLs is a later increment
(mirrors the Scrapling step deferred for System B).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from ..schema import Actor, Document


def _build_query(actor: Actor) -> str:
    """Actor name + the "quantum" domain anchor, NO geo bias.

    Deliberately simple: SearXNG's general engines (google-cse, brave, …) do
    NOT parse the `(A OR B)` OR-group syntax the Google-News RSS feed accepts —
    a query like `"IBM Research" (quantum OR qubit)` returns ZERO results,
    whereas `IBM Research quantum` returns dozens (measured live: IBM 63,
    ID Quantique 44, Terra Quantum 18 — vs 0/0/0 for the quoted-OR form). So we
    anchor on the bare name + "quantum" for maximum recall and let the Critic
    filter for relevance (the codebase's "wide funnel + strict Critic"
    principle). No `gl=CH` / "Switzerland" term — that geo-bias is exactly what
    suppressed global actors (IBM) in news.py.
    """
    return f"{actor.name.strip()} quantum"


def collect_websearch(
    actor: Actor,
    *,
    searxng_url: str,
    max_results: int = 10,
    timeout: float = 20.0,
) -> list[Document]:
    """Query the shared SearXNG JSON API for an actor; return Documents.

    Returns [] (fail-open) on any error or when `searxng_url` is unset, so a
    SearXNG outage never breaks the Retriever — the other collectors still run.
    """
    base = (searxng_url or "").strip().rstrip("/")
    if not base:
        return []

    params = {"q": _build_query(actor), "format": "json"}
    url = f"{base}/search?{urlencode(params)}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    now = datetime.now(timezone.utc)
    docs: list[Document] = []
    for result in (data.get("results") or [])[:max_results]:
        link = (result.get("url") or "").strip()
        title = (result.get("title") or "").strip()
        snippet = (result.get("content") or "").strip()
        if not link or not title:
            continue
        body = f"{title}\n\n{snippet}".strip()
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
