"""Tests for the EPO OPS patent collector.

All HTTP is mocked via httpx.MockTransport so the suite stays hermetic
(no creds, no internet) — the production behaviour is exercised at deploy
time by running the cron with credentials in .env.
"""

from __future__ import annotations

import json

import httpx
import pytest

from masfactory_system.collection import patents
from masfactory_system.schema import Actor

# Captured before any monkey-patching — avoids the recursion trap noted in
# tests/test_press.py.
_REAL_HTTPX_CLIENT = httpx.Client


def _actor() -> Actor:
    return Actor(
        slug="id-quantique",
        name="ID Quantique",
        category="private_company",
        homepage="https://www.idquantique.com",
    )


# A minimal, schema-realistic EPO OPS biblio-search JSON response.
SAMPLE_OPS_PAYLOAD = {
    "ops:world-patent-data": {
        "ops:biblio-search": {
            "ops:search-result": {
                "exchange-documents": {
                    "exchange-document": [
                        {
                            "@country": "CH",
                            "@doc-number": "123456",
                            "@kind": "A1",
                            "bibliographic-data": {
                                "invention-title": [
                                    {"@lang": "en", "$": "Quantum key distribution apparatus"},
                                    {"@lang": "de", "$": "Quantenschlüsselverteilungs-Vorrichtung"},
                                ],
                            },
                            "abstract": [
                                {
                                    "@lang": "en",
                                    "p": {"$": "A device for distributing quantum keys over fiber."},
                                },
                            ],
                        },
                        {
                            "@country": "WO",
                            "@doc-number": "2026000789",
                            "@kind": "A1",
                            "bibliographic-data": {
                                "invention-title": {"@lang": "en", "$": "Quantum random number generator"},
                            },
                            "abstract": {
                                "@lang": "en",
                                "p": [{"$": "An apparatus generating"}, {"$": "true random numbers."}],
                            },
                        },
                    ]
                }
            }
        }
    }
}


SAMPLE_TOKEN_PAYLOAD = {
    "access_token": "test-bearer-xyz",
    "expires_in": 1200,
    "token_type": "Bearer",
}


def _mock_client(
    token_payload: dict = SAMPLE_TOKEN_PAYLOAD,
    search_payload: dict = SAMPLE_OPS_PAYLOAD,
    *,
    search_status: int = 200,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if "auth/accesstoken" in str(request.url):
            return httpx.Response(200, json=token_payload)
        if "search/biblio" in str(request.url):
            return httpx.Response(search_status, json=search_payload)
        return httpx.Response(404, json={"error": "not mocked"})

    return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def reset_token_cache():
    """Each test starts with an empty token cache so prior tests' mocks don't
    leak. The module-level cache is the only mutable state in patents.py."""
    patents._token_cache["access_token"] = None
    patents._token_cache["expires_at"] = 0.0
    yield


def test_is_configured_requires_both_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EPO_OPS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)
    assert patents.is_configured() is False

    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    assert patents.is_configured() is False  # secret still missing

    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    assert patents.is_configured() is True


def test_collect_returns_empty_when_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cron must keep running even with no EPO keys — collector goes silent."""
    monkeypatch.delenv("EPO_OPS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)
    # Even if HTTP was mocked, we should short-circuit before any network call.
    monkeypatch.setattr(patents.httpx, "Client", lambda *a, **kw: _mock_client())
    assert patents.collect_patents(_actor()) == []


def test_build_cql_includes_actor_and_quantum_constraints() -> None:
    cql = patents._build_cql(_actor())
    assert 'pa="ID Quantique"' in cql
    # Quantum-relevant IPC OR title/abstract keyword
    for cls in patents.QUANTUM_IPC:
        assert f'ic="{cls}"' in cql
    assert "ti=quantum" in cql
    assert "ab=quantum" in cql
    # Quotes inside the actor name are stripped so they don't break the CQL
    cql2 = patents._build_cql(
        Actor(slug="x", name='Foo "Bar"', category="private_company")
    )
    assert 'pa="Foo Bar"' in cql2


def test_collect_parses_ops_response_into_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    monkeypatch.setattr(patents.httpx, "Client", lambda *a, **kw: _mock_client())

    docs = patents.collect_patents(_actor(), max_results=5)
    assert len(docs) == 2

    d0 = docs[0]
    assert d0.source_kind == "swissreg"
    assert d0.actor_slug == "id-quantique"
    assert "Quantum key distribution apparatus" in d0.title
    # English abstract was chosen over German title
    assert "fiber" in d0.text
    # Espacenet URL pattern + country + doc number
    assert d0.source_url == (
        "https://worldwide.espacenet.com/patent/search/publication/CH/123456"
    )
    assert len(d0.content_hash) == 64

    d1 = docs[1]
    # WO publication with multi-paragraph abstract (list, not dict)
    assert d1.source_url.endswith("/WO/2026000789")
    assert "An apparatus generating" in d1.text
    assert "true random numbers" in d1.text


def test_collect_respects_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    monkeypatch.setattr(patents.httpx, "Client", lambda *a, **kw: _mock_client())
    docs = patents.collect_patents(_actor(), max_results=1)
    assert len(docs) == 1


def test_collect_handles_404_as_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPS returns 404 for 'no hits' on some endpoints — treat as empty, not error."""
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    monkeypatch.setattr(
        patents.httpx, "Client",
        lambda *a, **kw: _mock_client(search_status=404),
    )
    assert patents.collect_patents(_actor()) == []


def test_collect_handles_token_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the OAuth response is missing an access_token, return [] rather than crash."""
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    monkeypatch.setattr(
        patents.httpx, "Client",
        lambda *a, **kw: _mock_client(token_payload={"error": "invalid_client"}),
    )
    assert patents.collect_patents(_actor()) == []


def test_collect_handles_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")

    class BadClient:
        def __init__(self, *a, **kw): ...
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **kw): raise httpx.ConnectError("simulated outage")
        def get(self, *a, **kw): raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(patents.httpx, "Client", BadClient)
    assert patents.collect_patents(_actor()) == []


def test_collect_skips_documents_without_publication_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed OPS rows (missing @country or @doc-number) are silently skipped."""
    payload = {
        "ops:world-patent-data": {
            "ops:biblio-search": {
                "ops:search-result": {
                    "exchange-documents": {
                        "exchange-document": [
                            {"@kind": "A1"},  # no country/doc-number
                            {
                                "@country": "EP",
                                "@doc-number": "3456789",
                                "@kind": "B1",
                                "bibliographic-data": {
                                    "invention-title": {"@lang": "en", "$": "Valid patent"},
                                },
                            },
                        ]
                    }
                }
            }
        }
    }
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")
    monkeypatch.setattr(
        patents.httpx, "Client",
        lambda *a, **kw: _mock_client(search_payload=payload),
    )
    docs = patents.collect_patents(_actor())
    assert len(docs) == 1
    assert docs[0].source_url.endswith("/EP/3456789")


def test_token_is_cached_within_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cache should make a second collect() not re-request the token within
    the lifetime window — important for the per-actor cron loop's HTTP budget."""
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "k")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "s")

    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if "auth/accesstoken" in str(request.url):
            token_requests += 1
            return httpx.Response(200, json=SAMPLE_TOKEN_PAYLOAD)
        return httpx.Response(200, json=SAMPLE_OPS_PAYLOAD)

    def factory(*a, **kw):
        return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(patents.httpx, "Client", factory)

    patents.collect_patents(_actor())
    patents.collect_patents(_actor())
    patents.collect_patents(_actor())
    # 3 collects but only 1 token request — the cache works.
    assert token_requests == 1
