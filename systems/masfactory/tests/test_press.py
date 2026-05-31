"""Tests for the press-release aggregator collector.

Network is mocked via httpx's MockTransport so the test is hermetic and the
suite stays runnable on the VPS at build time (no internet from the
build-check stage).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from masfactory_system.collection import press
from masfactory_system.schema import Actor

# Capture the *real* httpx.Client constructor before any monkey-patching so the
# mock factory below can build a Client without recursing into its own patched
# reference. This avoids the (very easy to fall into) trap of:
#     monkeypatch.setattr(press.httpx, "Client", lambda: httpx.Client(...))
# which is infinite recursion because press.httpx is the same module object as
# the global httpx, so the lambda's inner `httpx.Client(...)` is itself.
_REAL_HTTPX_CLIENT = httpx.Client


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Bing News Search</title>
    <item>
      <title>SQI announces CHF 50M quantum funding round</title>
      <link>https://www.prnewswire.com/news-releases/sqi-funding-12345.html</link>
      <description>The Swiss Quantum Initiative announced a new funding round...</description>
      <pubDate>Mon, 26 May 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>SQI partners with ETH Zurich on quantum networking</title>
      <link>https://www.businesswire.com/news/home/20260527/sqi-eth-partnership</link>
      <description>SQI and ETH Zurich launch a joint quantum networking testbed...</description>
      <pubDate>Tue, 27 May 2026 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _actor() -> Actor:
    return Actor(
        slug="sqi",
        name="Swiss Quantum Initiative",
        category="national_initiative",
        homepage="https://www.sqi.swiss",
    )


def _mock_client(rss: str = SAMPLE_RSS, *, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=rss, headers={"content-type": "application/rss+xml"})

    transport = httpx.MockTransport(handler)
    # Use the captured real constructor — avoids infinite recursion when this
    # function is called from inside a monkeypatched press.httpx.Client.
    return _REAL_HTTPX_CLIENT(transport=transport)


def test_query_is_quoted_and_pr_biased() -> None:
    """The query must wrap the actor name in quotes and add the OR-group of
    PR verbs — that's what differentiates this collector from Google News."""
    q = press._build_query(_actor())
    assert '"Swiss Quantum Initiative"' in q
    assert "quantum" in q
    # All PR keywords appear in the OR-group
    for kw in press.PR_KEYWORDS:
        assert kw in q
    assert "(" in q and " OR " in q and ")" in q


def test_collect_parses_rss_into_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: RSS in → Documents out with the right shape."""

    def fake_client_factory(*args, **kwargs) -> httpx.Client:
        return _mock_client()

    monkeypatch.setattr(press.httpx, "Client", fake_client_factory)

    docs = press.collect_press_releases(_actor(), max_results=5)
    assert len(docs) == 2
    d0 = docs[0]
    assert d0.source_kind == "news"
    assert d0.actor_slug == "sqi"
    assert "SQI announces CHF 50M" in d0.title
    assert d0.source_url.startswith("https://www.prnewswire.com/")
    assert isinstance(d0.fetched_at, datetime)
    assert d0.fetched_at.tzinfo is not None
    assert len(d0.content_hash) == 64  # sha256 hex


def test_collect_respects_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(press.httpx, "Client", lambda *a, **kw: _mock_client())
    docs = press.collect_press_releases(_actor(), max_results=1)
    assert len(docs) == 1


def test_network_failure_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """A collector must never break the graph — any exception → []."""

    def boom(*args, **kwargs):
        raise httpx.ConnectError("simulated outage")

    class BadClient:
        def __init__(self, *a, **kw): ...
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *a, **kw):
            raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(press.httpx, "Client", BadClient)
    docs = press.collect_press_releases(_actor(), max_results=5)
    assert docs == []


def test_collect_skips_entries_without_link_or_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive — half-formed RSS entries are dropped, not raised."""
    rss = SAMPLE_RSS.replace(
        "<link>https://www.prnewswire.com/news-releases/sqi-funding-12345.html</link>",
        "<link></link>",
    )
    monkeypatch.setattr(press.httpx, "Client", lambda *a, **kw: _mock_client(rss))
    docs = press.collect_press_releases(_actor(), max_results=5)
    # First entry dropped (no link), second one kept.
    assert len(docs) == 1
    assert docs[0].source_url.startswith("https://www.businesswire.com/")
