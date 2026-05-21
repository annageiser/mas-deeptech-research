"""Smoke tests for the dashboard package (no network, no Streamlit runtime)."""

from __future__ import annotations

import pandas as pd

from dashboard_app.knowledge_graph import build_graph


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
    # 3 actor nodes + 2 dimension nodes = 5 nodes
    assert g.number_of_nodes() == 5
    # Actor-dimension edges: a1->research, a1->funding, a2->research, a2->funding, a3->research = 5
    # Actor-actor edges: a1 and a2 share 2 dims (>= threshold) → 1 edge.
    # Total: 5 + 1 = 6
    assert g.number_of_edges() == 6
    assert g.has_edge("a:a1", "a:a2")
    assert not g.has_edge("a:a1", "a:a3")  # only 1 shared dim < 2 threshold
