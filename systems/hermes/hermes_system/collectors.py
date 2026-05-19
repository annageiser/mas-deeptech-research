"""Lightweight collectors used by the Tools Registry.

These are deliberately written from scratch rather than imported from
`systems/masfactory/` — the two systems must remain code-independent so the
thesis's cross-system comparison is fair. The external behaviour (which API,
which scrape policy) is identical, which is what matters for the comparison.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from selectolax.parser import HTMLParser


ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"
USER_AGENT = "hermes-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"
WEB_CACHE_DIR = os.environ.get("HRM_WEB_CACHE_DIR", "/data/raw/hermes_web_cache")


def collect_arxiv_for_query(*, query: str, max_results: int, actor_slug: str) -> list[dict]:
    if not query.strip():
        return []
    url = (
        f"{ARXIV_ENDPOINT}?"
        + urlencode(
            {
                "search_query": f"all:{query.strip()}",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(max(1, min(20, int(max_results)))),
            }
        )
    )
    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
        resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    docs: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        link = entry.get("link") or ""
        if not (title and summary):
            continue
        body = f"{title}\n\n{summary}"
        docs.append(
            {
                "source_kind": "arxiv",
                "source_url": link,
                "actor_slug": actor_slug,
                "title": title,
                "text": body,
                "fetched_at": now,
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return docs


def _allowed(robots_url: str, target_url: str) -> bool:
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, target_url)
    except Exception:
        return False


def _cache_path(url: str) -> str:
    os.makedirs(WEB_CACHE_DIR, exist_ok=True)
    return os.path.join(WEB_CACHE_DIR, hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".html")


def collect_website_for_url(*, url: str, max_pages: int, actor_slug: str) -> list[dict]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return []
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if not _allowed(robots, url):
        return []
    cache = _cache_path(url)
    html: str | None = None
    if os.path.exists(cache):
        with open(cache, "r", encoding="utf-8") as fh:
            html = fh.read()
    if html is None:
        with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            try:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
            except Exception:
                return []
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(html)
        time.sleep(1.0)  # 1 req/sec/host

    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    text = tree.text(separator=" ", strip=True)[:12_000]
    if not text:
        return []
    return [
        {
            "source_kind": "website",
            "source_url": url,
            "actor_slug": actor_slug,
            "title": "",
            "text": text,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    ]
