"""Unit tests for the localextract provider's HTML helpers (v0.5.1, Stage 2b).

These cover the comparability-critical extraction logic that gives System B
full-text evidence matching System A (docs/iterations/v0.5.1-stage2b-system-b-
fulltext.md). The helpers live in a dependency-light module (`_html`) precisely
so they can be tested here without the upstream Hermes Agent image — CI adds
`plugins/web/localextract` to the path, so this imports as a top-level module.

`visible_text` MUST behave like System A's collection/website.py::_visible_text
(same tag-strip set, same separator, same cap); the thesis leans on that
equivalence, so regressions here are worth catching.
"""
from __future__ import annotations

from urllib.robotparser import RobotFileParser

import _html
from _html import page_title, robots_allowed, visible_text


# --------------------------------------------------------------------------
# visible_text — mirrors System A's extraction method
# --------------------------------------------------------------------------
def test_visible_text_strips_boilerplate_tags() -> None:
    html = (
        "<html><head><style>.x{color:red}</style></head>"
        "<body><nav>Home About</nav><header>Logo</header>"
        "<main>ETH Zurich announced a new qubit lab in 2026.</main>"
        "<script>track()</script><footer>Copyright</footer></body></html>"
    )
    text = visible_text(html)
    assert "ETH Zurich announced a new qubit lab in 2026." in text
    # Stripped tags must not leak into the extracted text.
    for boilerplate in ("Home About", "Logo", "track()", "Copyright", "color:red"):
        assert boilerplate not in text


def test_visible_text_joins_with_space() -> None:
    html = "<body><p>Quantum</p><p>Switzerland</p></body>"
    assert visible_text(html) == "Quantum Switzerland"


def test_visible_text_respects_max_chars() -> None:
    html = "<body><p>" + ("a" * 50_000) + "</p></body>"
    assert len(visible_text(html)) == _html.MAX_CHARS
    assert len(visible_text(html, max_chars=100)) == 100


def test_visible_text_empty_on_no_body_text() -> None:
    html = "<html><head><title>only title</title></head><body></body></html>"
    assert visible_text(html) == ""


# --------------------------------------------------------------------------
# page_title
# --------------------------------------------------------------------------
def test_page_title_extracted() -> None:
    html = "<html><head><title>ID Quantique — News</title></head><body>x</body></html>"
    assert page_title(html) == "ID Quantique — News"


def test_page_title_absent_returns_empty() -> None:
    assert page_title("<html><body>no title here</body></html>") == ""


# --------------------------------------------------------------------------
# robots_allowed — fail-open policy + explicit Disallow + caching
# --------------------------------------------------------------------------
def test_robots_invalid_url_blocked() -> None:
    assert robots_allowed({}, "not-a-url") is False


def test_robots_explicit_disallow_respected() -> None:
    rp = RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /private"])
    cache = {"https://example.com": rp}
    assert robots_allowed(cache, "https://example.com/news/article") is True
    assert robots_allowed(cache, "https://example.com/private/secret") is False


def test_robots_fail_open_sentinel_allows() -> None:
    # A host whose robots.txt was unreachable is cached as allow-all → allowed
    # without any further network access.
    cache = {"https://example.com": _html._ROBOTS_ALLOW_ALL}
    assert robots_allowed(cache, "https://example.com/anything") is True


def test_robots_cache_populated_once_per_host() -> None:
    rp = RobotFileParser()
    rp.parse(["User-agent: *", "Allow: /"])
    cache = {"https://example.com": rp}
    # Second URL on the same host must reuse the cached parser (identity check),
    # i.e. no network read replaces it.
    robots_allowed(cache, "https://example.com/a")
    assert cache["https://example.com"] is rp


# --------------------------------------------------------------------------
# _fetch_robots — bounded httpx fetch + fail-open (the v0.5.1 robots-hang fix)
# --------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_fetch_robots_timeout_fails_open(monkeypatch) -> None:
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", _boom)
    assert _html._fetch_robots("https://slow.example") is _html._ROBOTS_ALLOW_ALL


def test_fetch_robots_non_200_fails_open(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(404, "irrelevant"))
    assert _html._fetch_robots("https://example.com") is _html._ROBOTS_ALLOW_ALL


def test_fetch_robots_200_parses_disallow(monkeypatch) -> None:
    import httpx

    body = "User-agent: *\nDisallow: /private\n"
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(200, body))
    rp = _html._fetch_robots("https://example.com")
    assert rp is not _html._ROBOTS_ALLOW_ALL
    assert rp.can_fetch(_html.USER_AGENT, "https://example.com/news") is True
    assert rp.can_fetch(_html.USER_AGENT, "https://example.com/private/x") is False


def test_robots_allowed_uses_bounded_fetch_and_caches(monkeypatch) -> None:
    import httpx

    calls = {"n": 0}

    def _get(*a, **k):
        calls["n"] += 1
        return _FakeResp(200, "User-agent: *\nDisallow: /private\n")

    monkeypatch.setattr(httpx, "get", _get)
    cache: dict = {}
    assert robots_allowed(cache, "https://example.com/news/a") is True
    assert robots_allowed(cache, "https://example.com/private/b") is False
    # robots.txt fetched exactly once for the host despite two URL checks.
    assert calls["n"] == 1
