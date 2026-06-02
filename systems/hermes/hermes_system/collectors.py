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
BING_NEWS_ENDPOINT = "https://www.bing.com/news/search"
EPO_OPS_BASE = "https://ops.epo.org/3.2"
EPO_OPS_TOKEN_URL = f"{EPO_OPS_BASE}/auth/accesstoken"
EPO_OPS_SEARCH_URL = f"{EPO_OPS_BASE}/rest-services/published-data/search/biblio"
USER_AGENT = "hermes-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"
# Verbs that bias Bing News' ranker toward press-release-style content. Kept
# identical to systems/masfactory/collection/press.py so the comparative
# invariant holds (same external behaviour, code-independent implementations).
PR_KEYWORDS = ("announces", "launches", "partners", "funding", "breakthrough")
# Same quantum-relevant IPC classes as systems/masfactory/collection/patents.py.
QUANTUM_IPC = ("G06N10", "H04L9/0852")

# Module-level OAuth2 token cache for EPO OPS — independent of System A's
# cache (the two systems must not share state).
_epo_token_cache: dict[str, object] = {"access_token": None, "expires_at": 0.0}
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


def _arxiv_author_affiliations(entry) -> list[str]:
    """Pull <arxiv:affiliation> strings from a feedparser-parsed arXiv entry."""
    affs: list[str] = []
    for author in entry.get("authors") or []:
        aff = None
        if isinstance(author, dict):
            aff = author.get("arxiv_affiliation") or author.get("affiliation")
        else:
            aff = getattr(author, "arxiv_affiliation", None) or getattr(author, "affiliation", None)
        if aff:
            affs.append(str(aff))
    return affs


def _arxiv_belongs_to_actor(entry, *, actor_name: str, aliases: list[str]) -> bool:
    """Mirror of systems/masfactory/.../arxiv.py _belongs_to_actor.

    Same precision-over-recall posture: prefer affiliation tags; fall back
    to title/abstract mention only when no affiliation tags exist at all.
    """
    needles = [n.lower().strip() for n in [actor_name, *aliases] if n and n.strip()]
    if not needles:
        return True  # we have no way to check; let it through
    affs = _arxiv_author_affiliations(entry)
    if affs:
        haystack = " || ".join(affs).lower()
        return any(n in haystack for n in needles)
    # Fallback when the entry carries no affiliation tags at all.
    blob = ((entry.get("title") or "") + "\n" + (entry.get("summary") or "")).lower()
    return any(n in blob for n in needles)


def collect_arxiv_for_query(
    *,
    query: str,
    max_results: int,
    actor_slug: str,
    actor_name: str = "",
    aliases: list[str] | None = None,
    enforce_authorship: bool = True,
) -> list[dict]:
    """arXiv search, mirroring systems/masfactory/collection/arxiv.py.

    `enforce_authorship=True` (default) applies the author-affiliation
    check: each entry is kept only if some author's `<arxiv:affiliation>`
    matches `actor_name` or one of `aliases`. Same precision-over-recall
    framing as System A — papers that merely mention the actor in their
    body but not in any author affiliation are dropped.

    Backward-compat: `actor_name=""` (the default for old callers that
    haven't been updated) skips the check.
    """
    normalised = _normalise_arxiv_query(query)
    if not normalised:
        return []
    # Over-fetch when filtering to keep the post-filter yield close to
    # the requested max_results. 3x is empirically about right.
    requested = max(1, min(30, max_results * 3 if (enforce_authorship and actor_name) else max_results))
    url = (
        f"{ARXIV_ENDPOINT}?"
        + urlencode(
            {
                "search_query": normalised,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(requested),
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
    aliases = aliases or []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        link = entry.get("link") or ""
        if not (title and summary):
            continue
        if enforce_authorship and actor_name:
            if not _arxiv_belongs_to_actor(entry, actor_name=actor_name, aliases=aliases):
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
        if len(docs) >= max_results:
            break
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
    # Widened in v0.4.0: keyword OR-group covers quantum subfields
    # (computing / sensing / QKD). The Critic filters hard for actor +
    # quantum relevance so a wider funnel doesn't degrade the final corpus.
    q = f'"{actor_name.strip()}" (quantum OR qubit OR QKD)'
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


# ---------- EPO OPS patents (source_kind='swissreg') ----------

def _epo_token(client: httpx.Client) -> str | None:
    """OAuth2 client-credentials → access_token. Cached at module level for
    18 of the 20-minute token lifetime. Returns None if creds missing or
    the auth call fails — caller treats None as 'collector disabled'."""
    import time as _t
    from base64 import b64encode

    now = _t.time()
    cached_token = _epo_token_cache.get("access_token")
    cached_exp = _epo_token_cache.get("expires_at", 0.0)
    if cached_token and isinstance(cached_exp, (int, float)) and cached_exp > now + 30:
        return str(cached_token)

    key = os.environ.get("EPO_OPS_CONSUMER_KEY", "").strip()
    secret = os.environ.get("EPO_OPS_CONSUMER_SECRET", "").strip()
    if not key or not secret:
        return None

    basic = b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    try:
        resp = client.post(
            EPO_OPS_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            content="grant_type=client_credentials",
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return None

    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 0) or 0)
    if not token:
        return None
    _epo_token_cache["access_token"] = token
    _epo_token_cache["expires_at"] = now + max(60, expires_in - 120)
    return token


def _epo_extract(payload: dict, *, actor_slug: str, now_iso: str, max_results: int) -> list[dict]:
    """Mirror of patents._extract_documents — defensive walk of the OPS JSON."""

    def _as_list(x):
        if x is None:
            return []
        return x if isinstance(x, list) else [x]

    docs: list[dict] = []
    biblio_root = (
        payload.get("ops:world-patent-data", {})
        .get("ops:biblio-search", {})
        .get("ops:search-result", {})
        .get("exchange-documents", {})
    )
    for ex_doc_wrap in _as_list(biblio_root.get("exchange-document")):
        for ex_doc in _as_list(ex_doc_wrap):
            if not isinstance(ex_doc, dict):
                continue
            country = ex_doc.get("@country", "")
            doc_num = ex_doc.get("@doc-number", "")
            kind = ex_doc.get("@kind", "")
            if not country or not doc_num:
                continue
            publication_number = f"{country}{doc_num}{kind}"

            title = ""
            biblio = ex_doc.get("bibliographic-data", {})
            for t in _as_list(biblio.get("invention-title")):
                if not isinstance(t, dict):
                    continue
                lang = t.get("@lang", "")
                text = (t.get("$") or "").strip()
                if not text:
                    continue
                if lang == "en":
                    title = text
                    break
                if not title:
                    title = text
            if not title:
                title = f"Patent {publication_number}"

            abstract = ""
            for ab in _as_list(ex_doc.get("abstract")):
                if not isinstance(ab, dict):
                    continue
                lang = ab.get("@lang", "")
                text_blob = ab.get("p")
                if isinstance(text_blob, dict):
                    text = (text_blob.get("$") or "").strip()
                elif isinstance(text_blob, list):
                    text = " ".join(
                        (p.get("$") or "").strip() if isinstance(p, dict) else str(p)
                        for p in text_blob
                    ).strip()
                elif isinstance(text_blob, str):
                    text = text_blob.strip()
                else:
                    continue
                if not text:
                    continue
                if lang == "en":
                    abstract = text
                    break
                if not abstract:
                    abstract = text

            source_url = (
                "https://worldwide.espacenet.com/patent/search/publication/"
                f"{country}/{doc_num}"
            )
            body = (title + "\n\n" + abstract).strip()
            docs.append(
                {
                    "source_kind": "swissreg",
                    "source_url": source_url,
                    "actor_slug": actor_slug,
                    "title": title[:500],
                    "text": body[:8_000],
                    "fetched_at": now_iso,
                    "content_hash": hashlib.sha256(
                        f"{publication_number}|{title}".encode("utf-8")
                    ).hexdigest(),
                }
            )
            if len(docs) >= max_results:
                return docs
    return docs


def collect_patents_for_actor(
    *, actor_name: str, max_results: int, actor_slug: str
) -> list[dict]:
    """EPO Open Patent Services patent search. Returns [] without raising on
    missing credentials / OAuth failure / search failure. See System A's
    patents.py for the substantive justification (Spence 1973 costly signal,
    Ehrenthal 2026 schema weights). Code-independent from System A's
    implementation — same external behaviour, comparative-validity invariant."""
    if not actor_name.strip():
        return []
    if not (
        os.environ.get("EPO_OPS_CONSUMER_KEY", "").strip()
        and os.environ.get("EPO_OPS_CONSUMER_SECRET", "").strip()
    ):
        return []
    name = actor_name.replace('"', "").strip()
    ipc = " OR ".join(f'ic="{cls}"' for cls in QUANTUM_IPC)
    cql = f'pa="{name}" AND ({ipc} OR ti=quantum OR ab=quantum)'

    try:
        with httpx.Client(
            timeout=25.0,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            token = _epo_token(client)
            if not token:
                return []
            resp = client.get(
                EPO_OPS_SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={"q": cql, "Range": f"1-{max(1, min(20, int(max_results)))}"},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return []

    return _epo_extract(
        payload,
        actor_slug=actor_slug,
        now_iso=datetime.now(timezone.utc).isoformat(),
        max_results=max_results,
    )


# ---------- Press-release aggregator (broader-web channel #3) ----------

def collect_press_releases_for_actor(
    *, actor_name: str, max_results: int, actor_slug: str
) -> list[dict]:
    """Bing News RSS with a press-release-biased query.

    Distinct aggregator from Google News (different ranker, different
    underlying source mix). The OR-group of PR verbs nudges Bing's ranker
    toward PR-wire content. See `systems/masfactory/collection/press.py`
    for the substantive citations (Kolbe & Burnett 1991 triangulation;
    Spence 1973 / Ehrenthal 2026 on press releases as costly signals).
    Code-independent from System A's implementation by design — same
    external behaviour, no shared module.
    """
    if not actor_name.strip():
        return []
    or_group = " OR ".join(PR_KEYWORDS)
    # Widened in v0.4.0 — see masfactory/collection/press.py docstring.
    q = f'"{actor_name.strip()}" (quantum OR qubit) ({or_group})'
    url = f"{BING_NEWS_ENDPOINT}?{urlencode({'q': q, 'format': 'rss'})}"
    try:
        with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url, follow_redirects=True)
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
