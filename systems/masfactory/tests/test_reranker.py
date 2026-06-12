"""Tests for v0.4.23 — bge-reranker cross-encoder pre-filter.

Does NOT load the real cross-encoder model (~280MB, ~3s cold start).
The actual model round-trip is smoke-tested at deploy time via the
runner's `--limit-actors 2` flag with MASF_RERANKER=1.
"""

from __future__ import annotations

import pytest

from masfactory_system import reranker
from masfactory_system.reranker import compose_actor_query, compose_signal_doc


# ---------- env-var gates ----------

def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_RERANKER", raising=False)
    assert reranker.is_enabled() is False


def test_env_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "true", "yes", "on", "TRUE", "  1  "):
        monkeypatch.setenv("MASF_RERANKER", value)
        assert reranker.is_enabled() is True, f"failed for value={value!r}"


def test_env_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("", "0", "false", "no", "off", "anything-else"):
        monkeypatch.setenv("MASF_RERANKER", value)
        assert reranker.is_enabled() is False, f"failed for value={value!r}"


def test_score_pairs_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_RERANKER", raising=False)
    assert reranker.score_pairs("query", ["doc"]) is None


def test_score_pairs_returns_none_for_empty_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER", "1")
    assert reranker.score_pairs("", ["doc"]) is None
    assert reranker.score_pairs("   ", ["doc"]) is None


def test_score_pairs_returns_none_for_empty_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER", "1")
    assert reranker.score_pairs("query", []) is None


# ---------- threshold parsing ----------

def test_threshold_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_RERANKER_THRESHOLD", raising=False)
    assert reranker.threshold() == 0.0


def test_threshold_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER_THRESHOLD", "0.5")
    assert reranker.threshold() == 0.5


def test_threshold_invalid_falls_back_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER_THRESHOLD", "not-a-number")
    assert reranker.threshold() == 0.0


def test_threshold_clamps_above(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER_THRESHOLD", "999.0")
    assert reranker.threshold() == 10.0


def test_threshold_clamps_below(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_RERANKER_THRESHOLD", "-999.0")
    assert reranker.threshold() == -10.0


# ---------- query / doc composition ----------

def test_compose_actor_query_includes_name_and_category() -> None:
    q = compose_actor_query({
        "slug": "id-quantique",
        "name": "ID Quantique",
        "category": "private_company",
    })
    assert "ID Quantique" in q
    assert "quantum" in q.lower()
    assert "private company" in q  # underscore → space


def test_compose_actor_query_falls_back_to_slug() -> None:
    q = compose_actor_query({"slug": "id-quantique"})
    assert "id-quantique" in q


def test_compose_signal_doc_joins_key_fields() -> None:
    doc = compose_signal_doc({
        "title": "ID Quantique CHF 40M Series C",
        "evidence_quote": "announced the close of a CHF 40 million Series C",
        "summary": "ID Quantique closes Series C funding round.",
        "dimension": "funding_event",  # intentionally excluded
    })
    assert "Series C" in doc
    assert "ID Quantique CHF 40M" in doc
    # dimension is NOT included — cross-encoder judges raw evidence, not the
    # LLM's pre-existing label.
    assert "dimension" not in doc.lower()


def test_compose_signal_doc_handles_missing_fields() -> None:
    assert compose_signal_doc({}) == ""
    assert compose_signal_doc({"title": "only-title"}) == "only-title"
