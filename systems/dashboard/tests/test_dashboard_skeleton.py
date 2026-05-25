"""Smoke tests for the dashboard package (no network, no Streamlit runtime)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dashboard_app import labels as L
from dashboard_app.knowledge_graph import build_graph
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata, ecosystem_summary


def test_build_graph_empty():
    g = build_graph(pd.DataFrame(), pd.DataFrame())
    assert g.number_of_nodes() == 0
    assert g.number_of_edges() == 0


def test_build_graph_with_data():
    signals = pd.DataFrame(
        [
            {"actor_slug": "a1", "dimension": "research_output"},
            {"actor_slug": "a1", "dimension": "research_output"},
            {"actor_slug": "a1", "dimension": "funding_or_grant"},
            {"actor_slug": "a2", "dimension": "research_output"},
            {"actor_slug": "a2", "dimension": "funding_or_grant"},
            {"actor_slug": "a3", "dimension": "research_output"},
        ]
    )
    actors = pd.DataFrame(
        [
            {"slug": "a1", "name": "Actor One", "category": "university_or_research_hub"},
            {"slug": "a2", "name": "Actor Two", "category": "private_company"},
            {"slug": "a3", "name": "Actor Three", "category": "ecosystem_builder"},
        ]
    )
    g = build_graph(signals, actors, shared_dim_threshold=2)
    assert g.number_of_nodes() == 5
    assert g.number_of_edges() == 6
    assert g.has_edge("a:a1", "a:a2")
    assert not g.has_edge("a:a1", "a:a3")


# ---------- labels module ----------

def test_all_dimensions_have_label_and_weight():
    for k in L.DIMENSION_LABEL:
        assert k in L.DIMENSION_HINT, f"missing hint for {k}"
        assert k in L.DIMENSION_WEIGHT, f"missing weight for {k}"
        assert k in L.CAPABILITY_DIMENSIONS or k in L.LEGITIMACY_DIMENSIONS, f"{k} not in capability or legitimacy"

def test_all_categories_have_label_and_colour():
    for k in L.CATEGORY_LABEL:
        assert k in L.CATEGORY_COLOR, f"missing colour for {k}"

def test_label_helpers():
    assert L.dimension("research_output") == "Research output"
    assert L.dimension("totally_unknown_thing").endswith("Unknown Thing")
    assert L.category("private_company") == "Private company"
    assert L.system_label("masfactory") == "System A · MASFactory"
    assert L.source_kind("arxiv") == "arXiv paper"
    assert L.tech_label(True) == "Capability"
    assert L.tech_label(False) == "Legitimacy"


# ---------- scoring module ----------

def _now() -> datetime:
    return datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)


def _mk_signal(slug: str, dim: str, conf: float, days_ago: int) -> dict:
    return {
        "actor_slug": slug,
        "dimension": dim,
        "confidence": conf,
        "inserted_at": (_now() - timedelta(days=days_ago)).isoformat(),
    }


def test_actor_impact_empty():
    out = actor_impact_table(pd.DataFrame())
    assert out.empty
    assert "impact" in out.columns


def test_actor_impact_basic():
    sigs = pd.DataFrame(
        [
            _mk_signal("a1", "funding_or_grant", 0.9, 1),        # this week
            _mk_signal("a1", "research_output", 0.8, 2),         # this week
            _mk_signal("a1", "market_positioning", 0.6, 10),     # prev week
            _mk_signal("a2", "research_output", 0.5, 1),
        ]
    )
    out = actor_impact_table(sigs, now=_now())
    out = out.set_index("actor_slug")

    # a1 impact = 1.5*0.9 + 1.0*0.8 + 0.4*0.6 = 1.35 + 0.8 + 0.24 = 2.39
    assert out.loc["a1", "impact"] == pytest.approx(2.39, abs=0.01)
    # a2 impact = 1.0 * 0.5 = 0.5
    assert out.loc["a2", "impact"] == pytest.approx(0.5, abs=0.01)
    # a1 dimensions = 3, a2 = 1
    assert out.loc["a1", "diversity"] == 3
    assert out.loc["a2", "diversity"] == 1
    # a1 momentum: 2 (this week) - 1 (prev week) = +1
    assert out.loc["a1", "momentum"] == 1
    # a1 authority: capability = 1 (research_output), legitimacy = 2 (funding + positioning) → (1+1)/(1+2+2) = 2/5 = 0.4
    assert out.loc["a1", "authority"] == pytest.approx(0.4, abs=0.01)


def test_attach_actor_metadata():
    scores = pd.DataFrame([{"actor_slug": "a1", "impact": 5.0}])
    actors = pd.DataFrame([{"slug": "a1", "name": "Actor 1", "category": "private_company", "homepage": "x"}])
    out = attach_actor_metadata(scores, actors)
    assert out.iloc[0]["name"] == "Actor 1"
    assert out.iloc[0]["category"] == "private_company"


def test_ecosystem_summary():
    scores = pd.DataFrame(
        [
            {"actor_slug": "a1", "impact": 5.0, "momentum": 2},
            {"actor_slug": "a2", "impact": 2.0, "momentum": -1},
        ]
    )
    es = ecosystem_summary(scores)
    assert es["n_actors_with_signals"] == 2
    assert es["total_impact"] == 7.0
    assert es["total_momentum"] == 1
    assert es["top_actor"] == "a1"
