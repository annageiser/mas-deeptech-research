"""Tests for the SearXNG web-search collector (v0.5.0).

Network is mocked via httpx's MockTransport so the test is hermetic and the
suite stays runnable at build time (no internet from the build-check stage).
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from masfactory_system.collection import websearch
from masfactory_system.schema import Actor

# Capture the real constructor before monkeypatching so the mock factory can
# build a Client without recursing into its own patched reference (see the
# identical guard in test_press.py for the full explanation).
_REAL_HTTPX_CLIENT = httpx.Client


SAMPLE_JSON = json.dumps(
    {
        "results": [
            {
                "title": "IBM Commits Over $10 Billion to Quantum Computing",
                "url": "https://example.com/ibm-10b",
                "content": "IBM announced a $10 billion investment in quantum...",
                "score": 1.0,
            },
            {
                "title": "IBM and ETH Zurich Launch 10-Year Quantum Partnership",
                "url": "https://example.com/ibm-eth",
                "content": "A decade-long AI and quantum research collaboration...",
                "score": 0.9,
            },
        ]
    }
)


def _actor() -> Actor:
    # A GLOBAL actor — the case the gl=CH Google-News feed under-serves and
    # this collector is meant to fix.
    return Actor(
        slug="ibm-research-zurich",
        name="IBM Research",
        category="private_company",
        homepage="https://www.research.ibm.com/labs/zurich",
    )


def _mock_client(body: str = SAMPLE_JSON, *, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": "application/json"})

    return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler))


def test_query_anchors_name_and_quantum_no_geo_bias() -> None:
    q = websearch._build_query(_actor())
    assert "IBM Research" in q
    assert "quantum" in q
    # The whole point: NO Switzerland geo-restriction baked into the query.
    assert "gl=CH" not in q and "Switzerland" not in q
    # And NO parenthesized OR-group — it returns 0 results on SearXNG's engines
    # (measured), which is why we don't reuse the Google-News query shape.
    assert "(" not in q and " OR " not in q


def test_collect_parses_json_into_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websearch.httpx, "Client", lambda *a, **kw: _mock_client())
    docs = websearch.collect_websearch(_actor(), searxng_url="http://searxng:8080", max_results=10)
    assert len(docs) == 2
    d0 = docs[0]
    assert d0.source_kind == "news"
    assert d0.actor_slug == "ibm-research-zurich"
    assert "IBM Commits Over $10 Billion" in d0.title
    assert d0.source_url == "https://example.com/ibm-10b"
    assert isinstance(d0.fetched_at, datetime)
    assert d0.fetched_at.tzinfo is not None
    assert len(d0.content_hash) == 64  # sha256 hex


def test_empty_searxng_url_is_a_noop_without_touching_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-open: an unset SEARXNG_URL must return [] without a network call."""

    def boom(*a, **kw):
        raise AssertionError("must not construct a client when SEARXNG_URL is unset")

    monkeypatch.setattr(websearch.httpx, "Client", boom)
    assert websearch.collect_websearch(_actor(), searxng_url="") == []
    assert websearch.collect_websearch(_actor(), searxng_url="   ") == []


def test_collect_respects_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websearch.httpx, "Client", lambda *a, **kw: _mock_client())
    docs = websearch.collect_websearch(_actor(), searxng_url="http://s:8080", max_results=1)
    assert len(docs) == 1


def test_network_failure_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A collector must never break the graph — any exception → []."""

    class BadClient:
        def __init__(self, *a, **kw): ...
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, *a, **kw):
            raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(websearch.httpx, "Client", BadClient)
    assert websearch.collect_websearch(_actor(), searxng_url="http://s:8080") == []


def test_malformed_json_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websearch.httpx, "Client", lambda *a, **kw: _mock_client("not json at all"))
    assert websearch.collect_websearch(_actor(), searxng_url="http://s:8080") == []


def test_skips_results_without_url_or_title(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps(
        {
            "results": [
                {"title": "has no url", "url": "", "content": "x"},
                {"title": "", "url": "https://example.com/no-title", "content": "y"},
                {
                    "title": "IBM and ETH Zurich Launch 10-Year Quantum Partnership",
                    "url": "https://example.com/ibm-eth",
                    "content": "kept",
                },
            ]
        }
    )
    monkeypatch.setattr(websearch.httpx, "Client", lambda *a, **kw: _mock_client(body))
    docs = websearch.collect_websearch(_actor(), searxng_url="http://s:8080")
    assert len(docs) == 1
    assert docs[0].source_url == "https://example.com/ibm-eth"
