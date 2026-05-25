"""Lightweight website scraping.

Goals (in priority order):
1. **Accurate per-item URLs.** Each Document carries the URL of the *specific*
   page the text came from — never the homepage URL when the text is from an
   article. The Extractor uses `source_url` verbatim, so getting this right
   is the difference between a signal that says "see this article" and one
   that says "see this homepage".
2. Constraints kept simple: one host per call, 1 req/sec/host, robots.txt
   honoured, responses cached so re-runs are deterministic.

Strategy:
- Always fetch the homepage first.
- Discover RSS / Atom feeds from `<link rel="alternate">` tags. Fetch each
  feed; emit one Document per entry, with the entry's `link` as source_url
  and the entry's title + summary as text. **Feed entries are the cleanest
  per-article URLs we can get without a per-site HTML parser.**
- If no feed exists, fall back to discovering "news / press / blog"
  subpages by URL keyword and follow each one (depth-2 OK on news index
  pages so we can land on individual articles, not just the index).
- Cap total Documents per actor at `max_pages` (default 5) to bound cost.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from selectolax.parser import HTMLParser

from ..schema import Actor, Document


USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"
NEWSY_HINTS = (
    "news", "press", "blog", "publication", "media", "announcement",
    "story", "article", "post", "release", "insight", "update",
)
FEED_MIME_HINTS = ("rss", "atom", "xml")


# ---------- robots / cache ----------

def _allowed(robots_url: str, target: str) -> bool:
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, target)
    except Exception:
        return False


def _cache_path(cache_dir: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return os.path.join(cache_dir, f"{digest}.html")


def _read_cache(cache_dir: str, url: str) -> str | None:
    path = _cache_path(cache_dir, url)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return None


def _write_cache(cache_dir: str, url: str, html: str) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    with open(_cache_path(cache_dir, url), "w", encoding="utf-8") as fh:
        fh.write(html)


# ---------- HTML helpers ----------

def _visible_text(html: str, max_chars: int = 12_000) -> str:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    text = tree.text(separator=" ", strip=True)
    return text[:max_chars]


def _newsy_links(html: str, base_url: str, max_links: int = 5) -> list[str]:
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


def _feed_urls(html: str, base_url: str) -> list[str]:
    tree = HTMLParser(html)
    out: list[str] = []
    seen: set[str] = set()
    for link in tree.css("link[rel='alternate']"):
        href = link.attributes.get("href") or ""
        type_attr = (link.attributes.get("type") or "").lower()
        if not href:
            continue
        looks_like_feed = any(h in type_attr for h in FEED_MIME_HINTS) or any(
            h in href.lower() for h in FEED_MIME_HINTS
        )
        if not looks_like_feed:
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


# ---------- core collector ----------

def _fetch(client: httpx.Client, url: str, cache_dir: str, delay_seconds: float) -> str | None:
    html = _read_cache(cache_dir, url)
    if html is not None:
        return html
    try:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None
    _write_cache(cache_dir, url, html)
    time.sleep(delay_seconds)
    return html


def _docs_from_feed(actor: Actor, feed_xml: str, max_entries: int) -> list[Document]:
    """Each RSS / Atom entry becomes its own Document with its own URL."""
    parsed = feedparser.parse(feed_xml)
    out: list[Document] = []
    for entry in parsed.entries[:max_entries]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if not link or (not title and not summary):
            continue
        body = f"{title}\n\n{summary}".strip()
        out.append(
            Document(
                source_kind="website",
                source_url=link,
                actor_slug=actor.slug,
                title=title or actor.name,
                text=body[:12_000],
                fetched_at=datetime.now(timezone.utc),
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    return out


def collect_website(
    actor: Actor,
    *,
    max_pages: int = 3,
    cache_dir: str = "/data/raw/web_cache",
    timeout: float = 20.0,
    delay_seconds: float = 1.0,
) -> list[Document]:
    """Fetch up to `max_pages` Documents for an actor.

    Discovery order:
      1. Homepage (always, if reachable + robots-allowed).
      2. RSS / Atom feeds linked from the homepage. Each feed entry becomes
         its own Document with the entry's specific article URL.
      3. If still under quota, newsy subpages and (depth-2) the newsy links
         we find on those subpages — for actors without a feed.
    """
    if actor.homepage is None:
        return []

    homepage = str(actor.homepage)
    parsed = urlparse(homepage)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if not _allowed(robots, homepage):
        return []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en;q=0.9, de;q=0.8, fr;q=0.7",
    }
    docs: list[Document] = []

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        # ---- 1. Homepage ----
        home_html = _fetch(client, homepage, cache_dir, delay_seconds)
        if home_html is None:
            return []
        home_text = _visible_text(home_html)
        if home_text:
            docs.append(
                Document(
                    source_kind="website",
                    source_url=homepage,
                    actor_slug=actor.slug,
                    title=actor.name,
                    text=home_text,
                    fetched_at=datetime.now(timezone.utc),
                    content_hash=hashlib.sha256(home_text.encode("utf-8")).hexdigest(),
                )
            )

        if len(docs) >= max_pages:
            return docs[:max_pages]

        # ---- 2. RSS / Atom feeds ----
        feed_urls = _feed_urls(home_html, homepage)
        for feed_url in feed_urls:
            if len(docs) >= max_pages:
                break
            if not _allowed(robots, feed_url):
                continue
            feed_xml = _fetch(client, feed_url, cache_dir, delay_seconds)
            if not feed_xml:
                continue
            remaining = max_pages - len(docs)
            feed_docs = _docs_from_feed(actor, feed_xml, max_entries=remaining)
            docs.extend(feed_docs)

        if len(docs) >= max_pages:
            return docs[:max_pages]

        # ---- 3. Newsy subpages, depth-2 ----
        index_links = _newsy_links(home_html, homepage, max_links=max_pages)
        crawled: set[str] = {homepage}
        for url in index_links:
            if len(docs) >= max_pages:
                break
            if url in crawled or not _allowed(robots, url):
                continue
            crawled.add(url)
            page_html = _fetch(client, url, cache_dir, delay_seconds)
            if not page_html:
                continue
            text = _visible_text(page_html)
            if text:
                docs.append(
                    Document(
                        source_kind="website",
                        source_url=url,
                        actor_slug=actor.slug,
                        title=actor.name,
                        text=text,
                        fetched_at=datetime.now(timezone.utc),
                        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
                )
                if len(docs) >= max_pages:
                    break
            # Depth-2: follow more newsy links FROM this index page
            inner = _newsy_links(page_html, url, max_links=max_pages - len(docs))
            for inner_url in inner:
                if len(docs) >= max_pages:
                    break
                if inner_url in crawled or not _allowed(robots, inner_url):
                    continue
                crawled.add(inner_url)
                inner_html = _fetch(client, inner_url, cache_dir, delay_seconds)
                if not inner_html:
                    continue
                inner_text = _visible_text(inner_html)
                if not inner_text:
                    continue
                docs.append(
                    Document(
                        source_kind="website",
                        source_url=inner_url,
                        actor_slug=actor.slug,
                        title=actor.name,
                        text=inner_text,
                        fetched_at=datetime.now(timezone.utc),
                        content_hash=hashlib.sha256(inner_text.encode("utf-8")).hexdigest(),
                    )
                )

    return docs[:max_pages]
