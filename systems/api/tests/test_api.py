"""API smoke tests — no network. data_access is monkeypatched with fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api_app import data_access as da
from api_app.main import app


client = TestClient(app)


def _now_iso(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


@pytest.fixture(autouse=True)
def fake_data(monkeypatch):
    actors = pd.DataFrame([
        {"slug": "a1", "name": "Actor One", "category": "private_company", "homepage": "https://a1.ch", "arxiv_query": None, "notes": None},
        {"slug": "a2", "name": "Actor Two", "category": "university_or_research_hub", "homepage": "https://a2.ch", "arxiv_query": None, "notes": None},
    ])
    signals = pd.DataFrame([
        # a1: one high-cost (funding) + one low-cost (positioning)
        {"id": "s1", "run_id": "r1", "actor_slug": "a1", "system": "masfactory", "source_kind": "news",
         "source_url": "https://x/1", "title": "Funding round", "summary": "raised CHF 10m",
         "evidence_quote": "raised CHF 10 million", "dimension": "funding_event",
         "is_technical": False, "confidence": 0.9, "inserted_at": _now_iso(1)},
        {"id": "s2", "run_id": "r1", "actor_slug": "a1", "system": "masfactory", "source_kind": "website",
         "source_url": "https://x/2", "title": "Roadmap", "summary": "leading provider",
         "evidence_quote": "the leading provider", "dimension": "roadmaps",
         "is_technical": False, "confidence": 0.6, "inserted_at": _now_iso(1)},
        # a2: one high-cost research output
        {"id": "s3", "run_id": "r2", "actor_slug": "a2", "system": "hermes", "source_kind": "arxiv",
         "source_url": "https://x/3", "title": "New paper", "summary": "qubit result",
         "evidence_quote": "we demonstrate", "dimension": "publications",
         "is_technical": True, "confidence": 0.8, "inserted_at": _now_iso(2)},
    ])
    runs = pd.DataFrame([
        {"id": "r1", "system": "masfactory", "status": "ok", "started_at": _now_iso(1),
         "finished_at": _now_iso(1), "actor_slugs": ["a1"], "error_message": None},
        {"id": "r2", "system": "hermes", "status": "ok", "started_at": _now_iso(2),
         "finished_at": _now_iso(2), "actor_slugs": ["a2"], "error_message": None},
    ])
    tokens = pd.DataFrame([
        {"run_id": "r1", "node_name": "graph_total", "model_name": "m", "input_tokens": 1000,
         "output_tokens": 500, "calls": 0, "recorded_at": _now_iso(1), "system": "masfactory"},
        {"run_id": "r2", "node_name": "ai_agent", "model_name": "m", "input_tokens": 3000,
         "output_tokens": 800, "calls": 5, "recorded_at": _now_iso(2), "system": "hermes"},
    ])

    monkeypatch.setattr(da, "actors", lambda: actors)
    monkeypatch.setattr(da, "signals", lambda system=None, days=30: signals if system is None else signals[signals["system"] == system])
    monkeypatch.setattr(da, "runs", lambda system=None, days=30: runs if system is None else runs[runs["system"] == system])
    monkeypatch.setattr(da, "token_usage", lambda system=None, days=30: tokens if system is None else tokens[tokens["system"] == system])
    yield


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_meta_has_three_axes():
    r = client.get("/api/meta")
    assert r.status_code == 200
    dims = r.json()["dimensions"]
    assert len(dims) == 9
    d = {x["key"]: x for x in dims}
    assert d["funding_event"]["signal_cost"] == "high"
    assert d["roadmaps"]["signal_cost"] == "low"
    assert "observability" in d["publications"]
    assert d["roadmaps"]["cost_multiplier"] == 0.4


def test_scores_credibility_discounts_cheap_talk():
    r = client.get("/api/scores")
    assert r.status_code == 200
    scores = {s["actor_slug"]: s for s in r.json()["scores"]}
    a1 = scores["a1"]
    # a1 impact = funding(1.5*0.9) + positioning(0.4*0.6) = 1.35 + 0.24 = 1.59
    assert a1["impact"] == pytest.approx(1.59, abs=0.01)
    # credibility = 1.35*1.0 + 0.24*0.4 = 1.35 + 0.096 = 1.446 → 1.45
    assert a1["credibility"] == pytest.approx(1.45, abs=0.01)
    # cheap_talk_ratio = 1 low-cost / 2 signals = 0.5
    assert a1["cheap_talk_ratio"] == pytest.approx(0.5, abs=0.01)


def test_signalling_endpoint():
    r = client.get("/api/signalling")
    assert r.status_code == 200
    body = r.json()
    # 3 signals: 2 high (funding, research) + 1 low (positioning); medium=0
    assert body["cost_mix"]["high"] == 2
    assert body["cost_mix"]["low"] == 1
    assert body["ecosystem_cheap_talk_ratio"] == pytest.approx(1 / 3, abs=0.01)


def test_actor_detail_and_rank():
    r = client.get("/api/actor/a1")
    assert r.status_code == 200
    body = r.json()
    assert body["actor"]["name"] == "Actor One"
    assert body["score"]["signal_count"] == 2
    assert len(body["signals"]) == 2


def test_actor_404():
    assert client.get("/api/actor/does-not-exist").status_code == 404


def test_compare_ab():
    r = client.get("/api/compare")
    assert r.status_code == 200
    body = r.json()
    assert body["per_system"]["masfactory"]["signals"] == 2
    assert body["per_system"]["hermes"]["signals"] == 1
    # a1 only in A, a2 only in B
    counts = body["agreement_counts"]
    assert counts["only_a"] == 1
    assert counts["only_b"] == 1


def test_knowledge_graph():
    r = client.get("/api/knowledge-graph?threshold=1")
    assert r.status_code == 200
    body = r.json()
    actor_nodes = [n for n in body["nodes"] if n["kind"] == "actor"]
    assert len(actor_nodes) == 2


def test_ecosystem():
    r = client.get("/api/ecosystem")
    assert r.status_code == 200
    body = r.json()
    assert body["actors_total"] == 2
    assert body["summary"]["n_actors_with_signals"] == 2
