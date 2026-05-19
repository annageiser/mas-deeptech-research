"""Lightweight website scraping.

Fetches the actor homepage, extracts visible text + a small set of obvious
"news / press / blog" links (best-effort), and returns one Document per
fetched page. The result lands in the Extractor for signal mining.

Constraints baked in here so we don't have to defend them later:
- single host per call
- 1 second between requests to the same host
- robots.txt is checked before any fetch
- responses are cached by URL hash so re-runs are deterministic
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.parser import HTMLParser

from ..schema import Actor, Document


USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"
NEWSY_HINTS = ("news", "press", "blog", "publication", "media", "announcement", "story")


def _allowed(robots_url: str, target: str) -> bool:
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, target)
    except Exception:
        # If robots.txt can't be read we err on the side of skipping.
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


def _visible_text(html: str, max_chars: int = 12_000) -> str:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    text = tree.text(separator=" ", strip=True)
    return text[:max_chars]


def _newsy_links(html: str, base_url: str, max_links: int = 3) -> list[str]:
    tree = HTMLParser(html)
    candidates: list[str] = []
    seen: set[str] = set()
    for anchor in tree.css("a[href]"):
        href = anchor.attributes.get("href") or ""
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != urlparse(base_url).netloc:
            continue
        if not any(hint in absolute.lower() for hint in NEWSY_HINTS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        candidates.append(absolute)
        if len(candidates) >= max_links:
            break
    return candidates


def collect_website(
    actor: Actor,
    *,
    max_pages: int = 2,
    cache_dir: str = "/data/raw/web_cache",
    timeout: float = 20.0,
    delay_seconds: float = 1.0,
) -> list[Document]:
    """Fetch up to `max_pages` pages from the actor's homepage region."""
    if actor.homepage is None:
        return []

    homepage = str(actor.homepage)
    parsed = urlparse(homepage)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if not _allowed(robots, homepage):
        return []

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.9, de;q=0.8, fr;q=0.7"}
    docs: list[Document] = []

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        urls_to_fetch = [homepage]
        for url in urls_to_fetch:
            if len(docs) >= max_pages:
                break
            if not _allowed(robots, url):
                continue

            html = _read_cache(cache_dir, url)
            if html is None:
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                except Exception:
                    continue
                _write_cache(cache_dir, url, html)
                time.sleep(delay_seconds)

            text = _visible_text(html)
            if not text:
                continue

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

            if len(urls_to_fetch) < max_pages:
                urls_to_fetch.extend(_newsy_links(html, url, max_links=max_pages - len(urls_to_fetch)))

    return docs
