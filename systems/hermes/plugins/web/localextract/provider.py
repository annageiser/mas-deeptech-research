"""Local full-text web-extract provider — httpx + selectolax.

v0.5.1 (Stage 2b) — gives System B (Hermes) the *same* full-text extraction
capability System A (MASFactory) already has, so the A-vs-B comparison
isolates orchestration (modular graph vs agentic loop), not evidence depth.

WHY A PROVIDER, NOT A SKILL
---------------------------
The reference design (docs/iterations/v0.5.0-reference-architecture-retrieval.md,
§4.2) originally proposed a `scrapling` *skill*. That was abandoned: scrapling
is heavy (pulls Playwright/curl_cffi/camoufox) and its extractor returned near-
empty on real actor pages. It also left an unresolved blocker — whether the
agentic loop (toolsets `web,skills`, no terminal) can execute a skill CLI at
all. This provider sidesteps both problems: it plugs into the agent's ALREADY-
EXISTING built-in `web_extract` tool (which the model is nudged to prefer), so
no skill-CLI execution is needed and nothing new appears in the tool surface.

COMPARABILITY (the point of the thesis)
---------------------------------------
`_visible_text()` is a byte-for-byte re-implementation of System A's
masfactory_system/collection/website.py::_visible_text — same tag-strip set
(script/style/noscript/header/footer/nav), same
`HTMLParser(html).text(separator=" ", strip=True)`, same 12k char cap. It is a
SEPARATE implementation (the comparison-validity invariant forbids System B
importing masfactory code), but the *method* is identical, which is exactly
what makes the two systems' evidence layers comparable.

DISPATCH SHAPE
--------------
`web_extract_tool` (upstream tools/web_tools.py) resolves the provider named by
`web.extract_backend`, checks `supports_extract()`, then calls
`extract(urls, format=...)` and expects a list of dicts:

    [{"url", "title", "content", "raw_content", "metadata"?, "error"?}, ...]

Long pages (>~5000 chars) are then LLM-summarised by the tool's auxiliary
model (our free llama-3.3-70b) into `content`, keeping `raw_content` verbatim;
short pages stay verbatim. This mirrors System A, whose Extractor also reads
the text through an LLM. See the iteration doc for the verbatim-fidelity note.

SSRF / safety: upstream filters private/internal URLs via `async_is_safe_url`
BEFORE calling this provider, so we only see public URLs. We still respect
robots.txt (fail-open on fetch error), send an honest User-Agent, cap size,
and rate-limit to 1 req/sec/host for politeness (design doc §8).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from agent.web_search_provider import WebSearchProvider

from plugins.web.localextract._html import (
    MAX_CHARS,
    USER_AGENT,
    page_title as _page_title,
    robots_allowed as _robots_allowed,
    visible_text as _visible_text,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "localextract"

FETCH_TIMEOUT = 20.0
POLITENESS_DELAY = 1.0  # seconds between fetches to the same host


class LocalExtractProvider(WebSearchProvider):
    """Full-text extraction via a plain httpx GET + selectolax parse.

    Extract-only: pair with SearXNG (search) — set in cli-config.yaml as
    ``web.search_backend: searxng`` + ``web.extract_backend: localextract``.
    """

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Local full-text (httpx + selectolax)"

    def is_available(self) -> bool:
        """True when selectolax + httpx import — no API key, no network probe."""
        try:
            import httpx  # noqa: F401
            import selectolax  # noqa: F401

            return True
        except Exception:
            return False

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch each URL and return visible text in the web_extract shape.

        ``kwargs`` may carry ``format`` / ``include_raw`` / ``max_chars`` —
        we honour ``max_chars`` if given and ignore the rest (per the base
        class contract).
        """
        import httpx

        max_chars = int(kwargs.get("max_chars") or MAX_CHARS)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
            "Accept-Language": "en;q=0.9, de;q=0.8, fr;q=0.7",
        }
        robots_cache: Dict[str, Any] = {}
        last_fetch_by_host: Dict[str, float] = {}
        out: List[Dict[str, Any]] = []

        with httpx.Client(
            timeout=FETCH_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            for url in urls:
                if not _robots_allowed(robots_cache, url):
                    out.append(
                        {
                            "url": url,
                            "title": "",
                            "content": "",
                            "raw_content": "",
                            "error": "Blocked by robots.txt",
                        }
                    )
                    continue

                # 1 req/sec/host politeness (design doc §8).
                host = urlparse(url).netloc
                prev = last_fetch_by_host.get(host)
                if prev is not None:
                    wait = POLITENESS_DELAY - (time.monotonic() - prev)
                    if wait > 0:
                        time.sleep(wait)

                try:
                    resp = client.get(url)
                    last_fetch_by_host[host] = time.monotonic()
                    resp.raise_for_status()
                    html = resp.text
                except Exception as exc:  # noqa: BLE001
                    out.append(
                        {
                            "url": url,
                            "title": "",
                            "content": "",
                            "raw_content": "",
                            "error": f"Fetch failed: {exc}",
                        }
                    )
                    continue

                try:
                    text = _visible_text(html, max_chars=max_chars)
                    title = _page_title(html)
                except Exception as exc:  # noqa: BLE001
                    out.append(
                        {
                            "url": url,
                            "title": "",
                            "content": "",
                            "raw_content": "",
                            "error": f"Parse failed: {exc}",
                        }
                    )
                    continue

                if not text:
                    out.append(
                        {
                            "url": url,
                            "title": title,
                            "content": "",
                            "raw_content": "",
                            "error": "No visible text extracted",
                        }
                    )
                    continue

                out.append(
                    {
                        "url": url,
                        "title": title,
                        "content": text,
                        "raw_content": text,
                        "metadata": {
                            "extractor": "httpx+selectolax",
                            "chars": len(text),
                        },
                    }
                )

        logger.info(
            "localextract: extracted %d/%d URL(s)",
            sum(1 for r in out if not r.get("error")),
            len(urls),
        )
        return out

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Local full-text",
            "badge": "free · no key",
            "tag": (
                "Full-text extraction via httpx + selectolax (same method as "
                "System A). Pair with a search backend such as SearXNG."
            ),
            "env_vars": [],
        }
