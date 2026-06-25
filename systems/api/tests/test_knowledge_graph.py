"""Knowledge-graph builder tests — v0.4.40 additive layers.

Covers:
  - Backwards compatibility — default request shape matches pre-v0.4.40.
  - include_taxonomy=true adds the 4 signal_type nodes + taxonomy edges
    + actor-signal-type volume edges.
  - include_semantic=true emits semantic edges when embeddings populated.
  - include_semantic=true is a no-op when embeddings are NULL everywhere
    (the default operator-side state).
  - kg_model abstractions round-trip through to_wire correctly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api_app import data_access as da
from api_app.knowledge_graph import build_graph_json
from api_app.kg_model import (
    EdgeType,
    Entity,
    Graph,
    NodeType,
    Relationship,
    SemanticLink,
    actor_id,
    dimension_id,
    parse_id,
    signal_type_id,
)
from api_app.main import app


client = TestClient(app)


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ----------------------------- fixtures -----------------------------


def _make_actors():
    return pd.DataFrame([
        {"slug": "eth",  "name": "ETH Zurich",     "category": "university_or_research_hub"},
        {"slug": "idq",  "name": "ID Quantique",   "category": "private_company"},
        {"slug": "snf",  "name": "SNF",            "category": "national_initiative"},
    ])


def _make_signals(*, with_embeddings: bool = False):
    rows = [
        {"id": "s1", "run_id": "r", "actor_slug": "eth", "system": "masfactory",
         "source_kind": "arxiv", "source_url": "https://x/1", "title": "Paper A",
         "summary": "qubit", "evidence_quote": "we demonstrate",
         "dimension": "publications", "is_technical": True, "confidence": 0.8,
         "inserted_at": _iso(2)},
        {"id": "s2", "run_id": "r", "actor_slug": "eth", "system": "masfactory",
         "source_kind": "news", "source_url": "https://x/2", "title": "Patent E1",
         "summary": "ip", "evidence_quote": "filed today",
         "dimension": "patents", "is_technical": True, "confidence": 0.7,
         "inserted_at": _iso(3)},
        {"id": "s3", "run_id": "r", "actor_slug": "idq", "system": "hermes",
         "source_kind": "news", "source_url": "https://x/3", "title": "IDQ award",
         "summary": "award", "evidence_quote": "won",
         "dimension": "awards", "is_technical": False, "confidence": 0.6,
         "inserted_at": _iso(1)},
        {"id": "s4", "run_id": "r", "actor_slug": "idq", "system": "hermes",
         "source_kind": "news", "source_url": "https://x/4", "title": "IDQ paper",
         "summary": "paper", "evidence_quote": "we report",
         "dimension": "publications", "is_technical": True, "confidence": 0.7,
         "inserted_at": _iso(2)},
        {"id": "s5", "run_id": "r", "actor_slug": "snf", "system": "masfactory",
         "source_kind": "website", "source_url": "https://x/5", "title": "SNF call",
         "summary": "grant", "evidence_quote": "MAPS grant",
         "dimension": "funding_event", "is_technical": False, "confidence": 0.9,
         "inserted_at": _iso(1)},
    ]
    df = pd.DataFrame(rows)
    if with_embeddings:
        # Simulate two near-identical actors (eth + idq both publish) and
        # one outlier (snf). 4d vectors are enough to exercise the
        # cosine path; the real corpus uses 768d.
        df["embedding"] = [
            [1.0, 0.0, 0.0, 0.1],
            [0.95, 0.05, 0.0, 0.1],
            [0.97, 0.0, 0.05, 0.05],
            [0.93, 0.07, 0.0, 0.1],
            [0.0, 1.0, 0.0, 0.0],
        ]
    return df


# ----------------------------- direct builder -----------------------------


def test_build_default_is_backwards_compatible():
    """v0.4.39 clients see no new node/edge kinds when feature flags off."""
    graph = build_graph_json(_make_signals(), _make_actors())
    kinds = {n["kind"] for n in graph["nodes"]}
    edge_kinds = {e["kind"] for e in graph["edges"]}
    assert kinds == {"actor", "dimension"}
    assert edge_kinds <= {"actor-dim", "actor-actor"}


def test_taxonomy_adds_signal_type_nodes_and_edges():
    graph = build_graph_json(
        _make_signals(), _make_actors(), include_taxonomy=True,
    )
    kinds = {n["kind"] for n in graph["nodes"]}
    edge_kinds = {e["kind"] for e in graph["edges"]}
    assert "signal_type" in kinds
    assert "dim-signal-type" in edge_kinds
    assert "actor-signal-type" in edge_kinds

    # Each emitted signal_type should match one of the four Ehrenthal keys
    # AND should be reachable from at least one dimension via a taxonomy edge.
    st_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "signal_type"}
    dst_edges = {e["target"] for e in graph["edges"] if e["kind"] == "dim-signal-type"}
    assert st_ids == dst_edges


def test_semantic_no_op_without_embeddings():
    """Default operator state — MASF_EMBEDDINGS/HRM_EMBEDDINGS off —
    means the signals DataFrame carries no `embedding` column. The
    semantic layer must silently produce zero edges."""
    graph = build_graph_json(
        _make_signals(), _make_actors(), include_semantic=True,
    )
    sem_edges = [e for e in graph["edges"] if e["kind"] == "actor-actor-sim"]
    assert sem_edges == []


def test_semantic_edges_appear_when_embeddings_present():
    """eth + idq are similar; snf is the outlier — expect at least one
    pair above the default threshold and no edge to snf."""
    graph = build_graph_json(
        _make_signals(with_embeddings=True),
        _make_actors(),
        include_semantic=True,
        semantic_threshold=0.85,
    )
    sem_edges = [e for e in graph["edges"] if e["kind"] == "actor-actor-sim"]
    assert sem_edges, "expected at least one semantic edge"
    for e in sem_edges:
        assert "similarity" in e
        assert 0.85 <= e["similarity"] <= 1.0


def test_semantic_threshold_respected():
    graph = build_graph_json(
        _make_signals(with_embeddings=True),
        _make_actors(),
        include_semantic=True,
        semantic_threshold=0.999,  # impossibly tight
    )
    sem_edges = [e for e in graph["edges"] if e["kind"] == "actor-actor-sim"]
    assert sem_edges == []


# ----------------------------- HTTP route -----------------------------


@pytest.fixture
def patched_data_access(monkeypatch):
    actors = _make_actors()
    signals = _make_signals()
    embeddings = _make_signals(with_embeddings=True)[["id", "actor_slug", "embedding"]]

    monkeypatch.setattr(da, "actors", lambda: actors)
    monkeypatch.setattr(
        da, "signals",
        lambda system=None, days=30: signals if system is None else signals[signals["system"] == system],
    )
    monkeypatch.setattr(
        da, "signal_embeddings",
        lambda system=None, days=30: embeddings if system is None else embeddings.merge(
            signals[["id", "system"]], on="id", how="left"
        ).query("system == @system").drop(columns=["system"]),
    )


def test_route_backwards_compat(patched_data_access):
    r = client.get("/api/knowledge-graph")
    assert r.status_code == 200
    body = r.json()
    kinds = {n["kind"] for n in body["nodes"]}
    assert kinds == {"actor", "dimension"}


def test_route_taxonomy_flag(patched_data_access):
    r = client.get("/api/knowledge-graph?include_taxonomy=true")
    assert r.status_code == 200
    body = r.json()
    assert any(n["kind"] == "signal_type" for n in body["nodes"])
    assert any(e["kind"] == "dim-signal-type" for e in body["edges"])


def test_route_semantic_flag(patched_data_access):
    r = client.get("/api/knowledge-graph?include_semantic=true&semantic_threshold=0.85")
    assert r.status_code == 200
    body = r.json()
    sem_edges = [e for e in body["edges"] if e["kind"] == "actor-actor-sim"]
    assert sem_edges, "semantic edges should appear when embeddings present"


# ----------------------------- kg_model unit tests -----------------------------


def test_id_helpers_round_trip():
    assert parse_id(actor_id("eth")) == (NodeType.ACTOR, "eth")
    assert parse_id(dimension_id("patents")) == (NodeType.DIMENSION, "patents")
    assert parse_id(signal_type_id("legitimacy")) == (NodeType.SIGNAL_TYPE, "legitimacy")
    assert parse_id("unknown:foo") == (None, "foo")


def test_graph_to_wire_preserves_property_spread():
    g = Graph()
    g.add_entity(Entity(
        id=actor_id("eth"), type=NodeType.ACTOR, label="ETH",
        color="#abc", size=20,
        properties={"actor_slug": "eth", "category": "u"},
    ))
    g.add_entity(Entity(
        id=dimension_id("patents"), type=NodeType.DIMENSION, label="Patents",
        color="#def", size=14,
        properties={"dimension_key": "patents", "cost_class": "high"},
    ))
    g.add_relationship(Relationship(
        source=actor_id("eth"), target=dimension_id("patents"),
        type=EdgeType.ACTOR_TO_DIMENSION, weight=5.0,
        properties={"count": 5, "actor_label": "ETH"},
    ))
    wire = g.to_wire()
    assert wire["nodes"][0]["actor_slug"] == "eth"
    assert wire["nodes"][0]["category"] == "u"
    assert wire["edges"][0]["count"] == 5
    assert wire["edges"][0]["kind"] == "actor-dim"


def test_semantic_link_default_weight_from_similarity():
    link = SemanticLink(
        source=actor_id("a"), target=actor_id("b"),
        type=EdgeType.ACTOR_TO_ACTOR_SEMANTIC,
        similarity=0.91,
    )
    edge = link.to_edge()
    assert edge["weight"] == 0.91
    assert edge["similarity"] == 0.91
    assert edge["kind"] == "actor-actor-sim"
