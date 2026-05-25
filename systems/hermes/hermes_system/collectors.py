"""Lightweight collectors used by the Tools Registry.

Written from scratch — not imported from `systems/masfactory/` — so the two
systems remain code-independent for the comparative analysis. The external
behaviour (which API, which scrape policy, RSS-first article discovery) is
deliberately the same.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from selectolax.parser import HTMLParser


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
GNEWS_ENDPOINT = "https://news.google.com/rss/search"
USER_AGENT = "hermes-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"
WEB_CACHE_DIR = os.environ.get("HRM_WEB_CACHE_DIR", "/data/raw/hermes_web_cache")
NEWSY_HINTS = (
    "news", "press", "blog", "publication", "media", "announcement",
    "story", "article", "post", "release", "insight", "update",
)
FEED_MIME_HINTS = ("rss", "atom", "xml")


# ---------- arXiv ----------

_ARXIV_FIELD_PREFIXES = ("ti:", "au:", "abs:", "co:", "jr:", "cat:", "rn:", "id:", "all:", "aff:")


def _normalise_arxiv_query(raw: str) -> str:
    """Pass through `aff:` / `au:` etc. unchanged; wrap bare text as `all:`."""
    s = raw.strip()
    if not s:
        return ""
    lo = s.lower()
    if any(lo.startswith(p) for p in _ARXIV_FIELD_PREFIXES):
        return s
    return f"all:{s}"


# arXiv's terms ask for >=3s between requests. Module-level throttle keeps
# the Loop / agent from bursting requests across actors.
import threading as _threading
_ARXIV_MIN_INTERVAL = 3.1
_arxiv_last_call_at = 0.0
_arxiv_throttle_lock = _threading.Lock()


def _throttle_arxiv() -> None:
    global _arxiv_last_call_at
    with _arxiv_throttle_lock:
        elapsed = time.monotonic() - _arxiv_last_call_at
        if elapsed < _ARXIV_MIN_INTERVAL:
            time.sleep(_ARXIV_MIN_INTERVAL - elapsed)
        _arxiv_last_call_at = time.monotonic()


def collect_arxiv_for_query(*, query: str, max_results: int, actor_slug: str) -> list[dict]:
    normalised = _normalise_arxiv_query(query)
    if not normalised:
        return []
    url = (
        f"{ARXIV_ENDPOINT}?"
        + urlencode(
            {
                "search_query": normalised,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(max(1, min(20, int(max_results)))),
            }
        )
    )
    _throttle_arxiv()
    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
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


# ---------- web cache + helpers ----------

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


def _fetch_cached(url: str, headers: dict) -> str | None:
    cache = _cache_path(url)
    if os.path.exists(cache):
        with open(cache, "r", encoding="utf-8") as fh:
            return fh.read()
    try:
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None
    with open(cache, "w", encoding="utf-8") as fh:
        fh.write(html)
    time.sleep(1.0)  # 1 req/sec/host
    return html


def _visible_text(html: str, max_chars: int = 12_000) -> str:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    return tree.text(separator=" ", strip=True)[:max_chars]


def _feed_urls(html: str, base_url: str) -> list[str]:
    tree = HTMLParser(html)
    out: list[str] = []
    seen: set[str] = set()
    for link in tree.css("link[rel='alternate']"):
        href = link.attributes.get("href") or ""
        type_attr = (link.attributes.get("type") or "").lower()
        if not href:
            continue
        if not (any(h in type_attr for h in FEED_MIME_HINTS) or any(h in href.lower() for h in FEED_MIME_HINTS)):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def _newsy_links(html: str, base_url: str, max_links: int) -> list[str]:
    tree = HTMLParser(html)
    out: list[str] = []
    seen: set[str] = set()
    base_host = urlparse(base_url).netloc
    for anchor in tree.css("a[href]"):
        href = anchor.attributes.get("href") or ""
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != base_host:
            continue
        if not any(hint in absolute.lower() for hint in NEWSY_HINTS):
            continue
        if absolute in seen or absolute == base_url:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= max_links:
            break
    return out


def _doc_from_html(*, url: str, html: str, actor_slug: str, title_hint: str = "") -> dict | None:
    text = _visible_text(html)
    if not text:
        return None
    return {
        "source_kind": "website",
        "source_url": url,
        "actor_slug": actor_slug,
        "title": title_hint,
        "text": text,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _docs_from_feed(*, feed_xml: str, actor_slug: str, max_entries: int) -> list[dict]:
    parsed = feedparser.parse(feed_xml)
    out: list[dict] = []
    for entry in parsed.entries[:max_entries]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if not link or (not title and not summary):
            continue
        body = f"{title}\n\n{summary}".strip()
        out.append(
            {
                "source_kind": "website",
                "source_url": link,
                "actor_slug": actor_slug,
                "title": title,
                "text": body[:12_000],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return out


# ---------- public tool entry point ----------

def collect_website_for_url(*, url: str, max_pages: int, actor_slug: str) -> list[dict]:
    """Fetch a URL and (if it looks like a homepage) discover related articles.

    Returns one Document per page found, each with its own source_url. RSS /
    Atom feeds linked from the page are preferred over HTML link-following
    because feed entries already carry clean per-article URLs.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return []
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if not _allowed(robots, url):
        return []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en;q=0.9, de;q=0.8, fr;q=0.7",
    }

    docs: list[dict] = []
    home_html = _fetch_cached(url, headers)
    if not home_html:
        return []

    home_doc = _doc_from_html(url=url, html=home_html, actor_slug=actor_slug)
    if home_doc:
        docs.append(home_doc)
    if len(docs) >= max_pages:
        return docs[:max_pages]

    # Feeds linked from the page
    for feed_url in _feed_urls(home_html, url):
        if len(docs) >= max_pages:
            break
        if not _allowed(robots, feed_url):
            continue
        feed_xml = _fetch_cached(feed_url, headers)
        if not feed_xml:
            continue
        remaining = max_pages - len(docs)
        docs.extend(_docs_from_feed(feed_xml=feed_xml, actor_slug=actor_slug, max_entries=remaining))

    if len(docs) >= max_pages:
        return docs[:max_pages]

    # Newsy subpages
    for sub_url in _newsy_links(home_html, url, max_links=max_pages - len(docs)):
        if len(docs) >= max_pages:
            break
        if not _allowed(robots, sub_url):
            continue
        sub_html = _fetch_cached(sub_url, headers)
        if not sub_html:
            continue
        sub_doc = _doc_from_html(url=sub_url, html=sub_html, actor_slug=actor_slug)
        if sub_doc:
            docs.append(sub_doc)

    return docs[:max_pages]


# ---------- Google News (broader third-party coverage) ----------

def collect_google_news_for_actor(*, actor_name: str, max_results: int, actor_slug: str) -> list[dict]:
    """Fetch Google News RSS, biased to Switzerland.

    Same logic as systems/masfactory's collect_google_news — kept
    code-independent for the comparative invariant. Justified
    academically by Kolbe & Burnett 1991 (content analysis) and
    Suchman 1995 (legitimacy via third-party recognition).
    """
    if not actor_name.strip():
        return []
    # Loosened from `"<name>" quantum (Switzerland OR Swiss OR Suisse OR
    # Schweiz)` — the country filter was too restrictive. gl=CH on the
    # endpoint already biases toward Switzerland.
    q = f'"{actor_name.strip()}" quantum'
    url = f"{GNEWS_ENDPOINT}?{urlencode({'q': q, 'hl': 'en', 'gl': 'CH', 'ceid': 'CH:en'})}"
    try:
        with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception:
        return []
    feed = feedparser.parse(resp.text)
    docs: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for entry in feed.entries[: max(1, min(20, int(max_results)))]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if not link or not title:
            continue
        body = f"{title}\n\n{summary}".strip()
        docs.append(
            {
                "source_kind": "news",
                "source_url": link,
                "actor_slug": actor_slug,
                "title": title,
                "text": body[:8_000],
                "fetched_at": now,
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return docs
