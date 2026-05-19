"""RootGraph wiring for System A.

Linear pipeline matching the architecture diagram:

  ENTRY → Planner → Retriever → Extractor → Classifier → Critic → Analyst → Persistence → EXIT

The model is bound to all Agent nodes at runtime via
`template_defaults_for(type_filter=Agent, model=...)` (a context manager
exposed by MASFactory) — see `runner.py`. `build_graph()` itself takes no
model argument and works at image-build time without credentials.
"""

from __future__ import annotations

from masfactory import RootGraph

from .agents import (
    AnalystNode,
    ClassifierNode,
    CriticNode,
    ExtractorNode,
    PersistenceNode,
    PlannerNode,
    RetrieverNode,
)


WORKFLOW_ATTRIBUTES: dict[str, object] = {
    # ---- injected by runner ----
    "actor_pool": [],
    "limit_actors": 3,
    "limit_arxiv_per_actor": 5,
    "limit_website_pages_per_actor": 2,
    "web_cache_dir": "/data/raw/web_cache",
    "store": None,
    "audit_folder": None,
    "run_id": None,
    "config_snapshot": {},
    # ---- flows between nodes ----
    "candidate_actors_json": "",
    "plan_json": "",
    "documents": [],
    "documents_count": 0,
    "documents_json": "",
    "candidates_json": "",
    "classified_json": "",
    "critique_json": "",
    "surviving_signals_json": "",
    "brief_md": "",
    "signals_kept": 0,
    "signals_inserted": 0,
    "retriever_errors": [],
}


def build_graph() -> RootGraph:
    """Construct the workflow without binding a model.

    The runner wraps `build()` + `invoke()` in `template_defaults_for(Agent, model=...)`
    so every Agent node receives the live `LegacyOpenAIModel`.
    """
    g = RootGraph(
        name="masfactory_swiss_quantum",
        attributes=dict(WORKFLOW_ATTRIBUTES),
        nodes=[
            ("planner", PlannerNode),
            ("retriever", RetrieverNode),
            ("extractor", ExtractorNode),
            ("classifier", ClassifierNode),
            ("critic", CriticNode),
            ("analyst", AnalystNode),
            ("persistence", PersistenceNode),
        ],
        edges=[
            ("ENTRY", "planner", {"candidate_actors_json": "JSON list of candidate actors", "limit_actors": "Quota"}),
            ("planner", "retriever", {"plan_json": "Plan to execute"}),
            ("retriever", "extractor", {"documents_json": "Raw documents"}),
            ("extractor", "classifier", {"candidates_json": "Signal candidates"}),
            ("classifier", "critic", {"classified_json": "Classified signals"}),
            ("classifier", "persistence", {"classified_json": "Classified signals (for audit/upsert)"}),
            ("critic", "persistence", {"critique_json": "Critique decisions"}),
            ("critic", "analyst", {"surviving_signals_json": "Surviving signals after critic"}),
            ("analyst", "persistence", {"brief_md": "Markdown brief"}),
            ("persistence", "EXIT", {"signals_kept": "Count kept", "signals_inserted": "Count inserted"}),
        ],
    )
    return g
