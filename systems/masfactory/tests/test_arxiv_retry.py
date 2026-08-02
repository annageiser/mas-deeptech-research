"""arXiv transient failures must be retried, not silently lost.

retriever.py wraps every collector in `try/except Exception` and records the
error, which keeps one bad source from killing a run. The cost is that a
transient failure is indistinguishable from "this actor has no papers": the
run completes, the audit shows a retriever_error, and that actor's entire
publications channel is gone for the day.

That is what happened. The 2026-08-01 production run logged two arXiv read
timeouts and a 429, and System A recorded ZERO arxiv-sourced signals across
the whole of July while System B recorded 151. Read naively that is an
architectural difference between a fixed pipeline and an agent. It is not; it
is an unretried HTTP error.
"""

from __future__ import annotations

import httpx
import pytest

from masfactory_system.collection import arxiv


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Collapse the 3.1s politeness throttle and the backoff waits."""
    monkeypatch.setattr(arxiv, "_throttle", lambda: None)
    monkeypatch.setattr(arxiv.time, "sleep", lambda _s: None)


class _Client:
    """httpx.Client stand-in that replays a scripted sequence of outcomes."""

    def __init__(self, script, calls):
        self._script, self._calls = script, calls

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def get(self, url):
        self._calls.append(url)
        outcome = self._script[min(len(self._calls) - 1, len(self._script) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        req = httpx.Request("GET", url)
        return httpx.Response(outcome[0], text=outcome[1], request=req,
                              headers=outcome[2] if len(outcome) > 2 else None)


def _install(monkeypatch, script):
    calls: list[str] = []
    monkeypatch.setattr(arxiv.httpx, "Client",
                        lambda **kw: _Client(script, calls))
    return calls


OK = (200, "<feed/>")


def test_429_is_retried_and_then_succeeds(monkeypatch):
    calls = _install(monkeypatch, [
        (429, "slow down", {"Retry-After": "1"}),
        OK,
    ])
    resp = arxiv._get_with_retry("https://export.arxiv.org/api/query?x=1", timeout=5)
    assert resp.status_code == 200
    assert len(calls) == 2, "a 429 must not end the attempt"


def test_read_timeout_is_retried(monkeypatch):
    calls = _install(monkeypatch, [
        httpx.ReadTimeout("the read operation timed out"),
        httpx.ReadTimeout("again"),
        OK,
    ])
    resp = arxiv._get_with_retry("https://export.arxiv.org/api/query?x=1", timeout=5)
    assert resp.status_code == 200
    assert len(calls) == 3


def test_server_error_is_retried(monkeypatch):
    calls = _install(monkeypatch, [(503, "unavailable"), OK])
    assert arxiv._get_with_retry("https://x/q", timeout=5).status_code == 200
    assert len(calls) == 2


def test_a_bad_query_is_not_retried(monkeypatch):
    """400 means our query is malformed. Retrying it just wastes the budget
    and delays the rest of the run."""
    calls = _install(monkeypatch, [(400, "bad query")])
    with pytest.raises(httpx.HTTPStatusError):
        arxiv._get_with_retry("https://x/q", timeout=5)
    assert len(calls) == 1, "a permanent 4xx must fail fast"


def test_gives_up_after_the_attempt_budget(monkeypatch):
    calls = _install(monkeypatch, [(429, "no")] * 10)
    with pytest.raises(httpx.HTTPStatusError):
        arxiv._get_with_retry("https://x/q", timeout=5)
    assert len(calls) == arxiv.ARXIV_MAX_ATTEMPTS


def test_success_first_time_costs_one_request(monkeypatch):
    calls = _install(monkeypatch, [OK])
    assert arxiv._get_with_retry("https://x/q", timeout=5).status_code == 200
    assert len(calls) == 1


def test_retry_after_header_is_honoured_over_our_backoff(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(arxiv.time, "sleep", lambda s: waits.append(s))
    _install(monkeypatch, [(429, "slow", {"Retry-After": "120"}), OK])

    arxiv._get_with_retry("https://x/q", timeout=5)

    assert waits and waits[0] == 120, (
        "the server's Retry-After must win over the local backoff guess"
    )


def test_throttle_still_applies_between_attempts(monkeypatch):
    """arXiv asks for >=3s between requests; retrying must not bypass that."""
    hits = []
    monkeypatch.setattr(arxiv, "_throttle", lambda: hits.append(1))
    _install(monkeypatch, [(429, "no"), OK])

    arxiv._get_with_retry("https://x/q", timeout=5)

    assert len(hits) == 2, "every attempt must go through the politeness throttle"
