"""Tests for the semantic-dedup config + helpers in persistence.

The Supabase RPC layer is mocked (no real DB). The pgvector index + the
SQL function itself are exercised in production by the daily cron;
hermetic unit tests cover the Python-side gate, threshold-clamping, and
the dedup decision logic.
"""

from __future__ import annotations

import pytest

from masfactory_system.agents.persistence import _semantic_dedup_config


# ---------- env gate + clamping ----------

def test_dedup_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_SEMANTIC_DEDUP", raising=False)
    enabled, _, _ = _semantic_dedup_config()
    assert enabled is False


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE", "  1  "])
def test_dedup_truthy_values(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP", raw)
    enabled, _, _ = _semantic_dedup_config()
    assert enabled is True


@pytest.mark.parametrize("raw", ["", "0", "false", "no", "off", "garbage"])
def test_dedup_falsy_values(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP", raw)
    enabled, _, _ = _semantic_dedup_config()
    assert enabled is False


def test_dedup_threshold_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_SEMANTIC_DEDUP_THRESHOLD", raising=False)
    _, threshold, _ = _semantic_dedup_config()
    assert threshold == pytest.approx(0.92)


@pytest.mark.parametrize("raw,expected", [
    ("0.85", 0.85),
    ("0.99", 0.99),
    ("0.5", 0.5),    # lower bound
    ("0.999", 0.999),  # upper bound
    ("0.1", 0.5),    # below lower bound → clamped
    ("1.5", 0.999),  # above upper bound → clamped
    ("garbage", 0.92),  # parse fail → default
])
def test_dedup_threshold_parses_and_clamps(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP_THRESHOLD", raw)
    _, threshold, _ = _semantic_dedup_config()
    assert threshold == pytest.approx(expected)


def test_dedup_days_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_SEMANTIC_DEDUP_DAYS", raising=False)
    _, _, days = _semantic_dedup_config()
    assert days == 90  # v0.4.0 raised default 30 → 90 (expanded scraping window)


@pytest.mark.parametrize("raw,expected", [
    ("7", 7),
    ("90", 90),
    ("365", 365),  # upper bound
    ("1", 1),       # lower bound
    ("0", 1),       # below lower → clamped
    ("999", 365),   # above upper → clamped
    ("garbage", 90),  # parse fail → default
])
def test_dedup_days_parses_and_clamps(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP_DAYS", raw)
    _, _, days = _semantic_dedup_config()
    assert days == expected


# ---------- end-to-end persistence dedup decision ----------

class _FakeStore:
    """Minimal SupabaseStore stand-in: records inserts + serves a single
    pre-canned near-neighbour result."""

    def __init__(self, near_neighbour: dict | None = None):
        self.near_neighbour = near_neighbour
        self.inserted: list = []
        self.queries: list = []

    def find_similar_signal(self, *, actor_slug, embedding, days_back):
        self.queries.append({
            "actor_slug": actor_slug,
            "embedding_len": len(embedding),
            "days_back": days_back,
        })
        return self.near_neighbour

    def insert_signals(self, rows):
        self.inserted.extend(rows)
        return len(rows)


class _NoopAudit:
    def __init__(self):
        self.payloads = {}

    def write_json(self, name, payload):
        self.payloads[name] = payload

    def write_text(self, name, payload):
        self.payloads[name] = payload


def _run_persist(*, surviving, store, audit, embed_on=False, sem_on=False, near=None):
    """Helper to invoke the persistence forward function under specific env."""
    import os
    from masfactory_system.agents import persistence as p_mod

    if embed_on:
        os.environ["MASF_EMBEDDINGS"] = "1"
    else:
        os.environ.pop("MASF_EMBEDDINGS", None)
    if sem_on:
        os.environ["MASF_SEMANTIC_DEDUP"] = "1"
    else:
        os.environ.pop("MASF_SEMANTIC_DEDUP", None)

    # Patch embed_text to return a deterministic stub vector if embeddings on
    if embed_on:
        p_mod.embed_text = lambda _text: [0.1] * 768  # noqa: ARG005
    else:
        p_mod.embed_text = lambda _text: None  # noqa: ARG005

    attrs = {
        "all_classified": [],
        "all_surviving_signals": surviving,
        "store": store,
        "audit_folder": audit,
        "run_id": "test-run",
        "documents": [
            {"actor_slug": s["actor_slug"], "source_url": s["source_url"]}
            for s in surviving
        ],
    }
    return p_mod._persist(None, attrs)


def test_semantic_dedup_drops_when_similarity_above_threshold(monkeypatch):
    """A signal whose nearest neighbour exceeds the threshold is dropped."""
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP_THRESHOLD", "0.90")
    store = _FakeStore(near_neighbour={
        "id": "existing-uuid",
        "title": "Existing signal",
        "source_url": "https://prior.example/article",
        "system": "masfactory",
        "similarity": 0.95,  # above threshold
        "inserted_at": "2026-05-01T00:00:00Z",
    })
    audit = _NoopAudit()
    surviving = [{
        "actor_slug": "sqi",
        "source_kind": "news",
        "source_url": "https://new.example/article",
        "title": "Near-duplicate news",
        "summary": "Same event from a different aggregator.",
        "evidence_quote": "SQI raises CHF 50M",
        "dimension": "funding_event",
        "is_technical": False,
        "confidence": 0.85,
    }]
    result = _run_persist(
        surviving=surviving, store=store, audit=audit,
        embed_on=True, sem_on=True,
    )
    assert result["signals_inserted"] == 0
    assert store.inserted == []  # nothing actually inserted
    assert len(store.queries) == 1
    # Audit log records the drop with both sides of the comparison
    dedup_blob = audit.payloads["semantic_dedup.json"]
    assert dedup_blob["enabled"] is True
    assert dedup_blob["signals_dropped"] == 1
    drop = dedup_blob["drops"][0]
    assert drop["matched_existing"]["id"] == "existing-uuid"
    assert drop["similarity"] == pytest.approx(0.95)


def test_semantic_dedup_keeps_when_similarity_below_threshold(monkeypatch):
    """A signal whose nearest neighbour is below the threshold is kept."""
    monkeypatch.setenv("MASF_SEMANTIC_DEDUP_THRESHOLD", "0.90")
    store = _FakeStore(near_neighbour={
        "id": "existing-uuid",
        "similarity": 0.80,  # below threshold
        "title": "Loosely related",
        "source_url": "https://prior.example/article",
        "system": "masfactory",
        "inserted_at": "2026-05-01T00:00:00Z",
    })
    audit = _NoopAudit()
    surviving = [{
        "actor_slug": "sqi",
        "source_kind": "news",
        "source_url": "https://new.example/article",
        "title": "Different angle",
        "summary": "Loosely related coverage.",
        "evidence_quote": "SQI also opened a new lab",
        "dimension": "hpc_collaborations",
        "is_technical": False,
        "confidence": 0.85,
    }]
    result = _run_persist(
        surviving=surviving, store=store, audit=audit,
        embed_on=True, sem_on=True,
    )
    assert result["signals_inserted"] == 1
    assert len(store.inserted) == 1
    dedup_blob = audit.payloads["semantic_dedup.json"]
    assert dedup_blob["signals_dropped"] == 0


def test_semantic_dedup_inactive_without_embeddings(monkeypatch):
    """sem_on without embed_on is a no-op (can't query without a vector)."""
    store = _FakeStore(near_neighbour={"id": "X", "similarity": 0.99})
    audit = _NoopAudit()
    surviving = [{
        "actor_slug": "sqi",
        "source_kind": "news",
        "source_url": "https://new.example/article",
        "title": "Signal",
        "summary": "...",
        "evidence_quote": "...",
        "dimension": "funding_event",
        "is_technical": False,
        "confidence": 0.85,
    }]
    result = _run_persist(
        surviving=surviving, store=store, audit=audit,
        embed_on=False, sem_on=True,  # sem on but embed off
    )
    # Should insert (dedup didn't run) AND should not have queried the store
    assert result["signals_inserted"] == 1
    assert store.queries == []
    # Audit shouldn't have the dedup blob either
    assert "semantic_dedup.json" not in audit.payloads


def test_semantic_dedup_no_neighbour_means_keep(monkeypatch):
    """If find_similar_signal returns None (no embedded signals for this
    actor yet), the candidate is kept."""
    store = _FakeStore(near_neighbour=None)
    audit = _NoopAudit()
    surviving = [{
        "actor_slug": "sqi",
        "source_kind": "news",
        "source_url": "https://new.example/article",
        "title": "First signal for this actor",
        "summary": "...",
        "evidence_quote": "...",
        "dimension": "funding_event",
        "is_technical": False,
        "confidence": 0.85,
    }]
    result = _run_persist(
        surviving=surviving, store=store, audit=audit,
        embed_on=True, sem_on=True,
    )
    assert result["signals_inserted"] == 1
    # Dedup logged but with zero drops
    dedup_blob = audit.payloads["semantic_dedup.json"]
    assert dedup_blob["signals_dropped"] == 0
