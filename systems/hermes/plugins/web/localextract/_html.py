"""Pure HTML→text helpers for the localextract provider (v0.5.1, Stage 2b).

Split out from provider.py deliberately: this module depends ONLY on
selectolax + the standard library (NO upstream `agent` import), so the
comparability-critical extraction logic can be unit-tested in the lightweight
hermes-bridge CI env without pulling the whole Hermes Agent image.

``visible_text`` is a byte-for-byte re-implementation of System A's
masfactory_system/collection/website.py::_visible_text — same tag-strip set,
same selectolax call, same 12k cap. Keeping the *method* identical (while the
*code* stays independent, per the comparison-validity invariant) is what makes
the two systems' evidence layers comparable.
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

# Honest, contactable UA — mirrors System A's website.py so a site operator
# sees the same bot identity from both systems.
USER_AGENT = (
    "masfactory-thesis/0.1 "
    "(+https://github.com/anna-geiser/mas-deeptech-research)"
)
# Match System A's cap so both systems feed comparably-sized text downstream.
MAX_CHARS = 12_000
# Bounded timeout for the robots.txt fetch. MUST be bounded: the stdlib
# RobotFileParser.read() uses urllib with NO timeout (global default is None),
# so a host that blackholes /robots.txt would hang extract() indefinitely and
# burn the actor's whole time budget. We fetch via httpx with this timeout.
ROBOTS_TIMEOUT = 10.0

# Cache sentinel: a host whose robots.txt was unreachable/unparseable → allow.
_ROBOTS_ALLOW_ALL = "allow-all"


def visible_text(html: str, max_chars: int = MAX_CHARS) -> str:
    """Extract visible text — identical method to System A's `_visible_text`."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    text = tree.text(separator=" ", strip=True)
    return text[:max_chars]


def page_title(html: str) -> str:
    """Return the document <title>, trimmed to 300 chars."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    node = tree.css_first("title")
    if node is not None:
        return (node.text(strip=True) or "")[:300]
    return ""


def _fetch_robots(host_key: str) -> Any:
    """Fetch ``<host>/robots.txt`` with a BOUNDED timeout; fail OPEN.

    Returns a parsed :class:`RobotFileParser` on HTTP 200, else the
    ``_ROBOTS_ALLOW_ALL`` sentinel (unreachable / non-200 / timeout / parse
    error → treated as allowed, per this provider's fail-open policy).

    Deliberately does NOT use ``RobotFileParser.read()`` — that calls
    ``urllib.request.urlopen`` with no timeout, so a host that blackholes
    ``/robots.txt`` would hang the whole extract() batch. httpx with
    ``ROBOTS_TIMEOUT`` bounds the wait.
    """
    import httpx

    try:
        resp = httpx.get(
            f"{host_key}/robots.txt",
            timeout=ROBOTS_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except Exception:
        return _ROBOTS_ALLOW_ALL
    # Only an explicit, fetchable robots body can carry a Disallow. Anything
    # else (404, 401/403, 5xx, empty) → fail open, matching the docstring.
    if resp.status_code != 200 or not resp.text:
        return _ROBOTS_ALLOW_ALL
    rp = RobotFileParser()
    try:
        rp.parse(resp.text.splitlines())
    except Exception:
        return _ROBOTS_ALLOW_ALL
    return rp


def robots_allowed(robots_cache: Dict[str, Any], url: str) -> bool:
    """Respect robots.txt, but fail OPEN on fetch/parse error.

    System A fails closed (it seeds a small fixed set of homepages and can
    afford to skip on any hiccup). Here the agent hands us public URLs it
    already surfaced via search, so a transient robots fetch failure should
    not silently blank the evidence — we only block on an *explicit* Disallow.
    Per-host result is cached so N URLs on one host fetch robots.txt once.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    host_key = f"{parsed.scheme}://{parsed.netloc}"
    if host_key not in robots_cache:
        robots_cache[host_key] = _fetch_robots(host_key)
    cached = robots_cache[host_key]
    if cached is _ROBOTS_ALLOW_ALL:
        return True
    try:
        return cached.can_fetch(USER_AGENT, url)
    except Exception:
        return True
