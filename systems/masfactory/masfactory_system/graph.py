"""RootGraph wiring for System A.

Strictly linear pipeline:

  ENTRY → Planner → Retriever → Extractor → Classifier → Critic
        → Survivor → Analyst → Persistence → EXIT

Sources the Retriever can pull per actor (sources field in plan_json):
  - "arxiv"   — papers from export.arxiv.org/api/query
  - "website" — actor homepage + RSS feeds + newsy subpages (depth 2)
  - "news"    — third-party coverage via Google News RSS, Switzerland-biased
                (Kolbe & Burnett 1991 — broader content analysis;
                 Suchman 1995 — strategic vs cognitive legitimacy is more
                 honest when both actor-controlled and third-party
                 sources are sampled).

Survivor (a small CustomNode) is the bridge between Critic and Analyst:
it filters the classified signals by the Critic's keep-decisions and
emits `surviving_signals_json` so the Analyst can write its brief from
real data. Without this bridge the Analyst saw an empty input and was
filling in plausible-sounding content from the model's training data —
a silent correctness bug discovered in the 2026-05-25 04:00 audit folder.

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
    SurvivorNode,
)


WORKFLOW_ATTRIBUTES: dict[str, object] = {
    # ---- injected by runner ----
    "actor_pool": [],
    "limit_actors": 3,
    "limit_arxiv_per_actor": 5,
    "limit_website_pages_per_actor": 5,
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
    g = RootGraph(
        name="masfactory_swiss_quantum",
        attributes=dict(WORKFLOW_ATTRIBUTES),
        nodes=[
            ("planner", PlannerNode),
            ("retriever", RetrieverNode),
            ("extractor", ExtractorNode),
            ("classifier", ClassifierNode),
            ("critic", CriticNode),
            ("survivor", SurvivorNode),
            ("analyst", AnalystNode),
            ("persistence", PersistenceNode),
        ],
        edges=[
            ("ENTRY", "planner", {"candidate_actors_json": "JSON list of candidate actors", "limit_actors": "Quota"}),
            ("planner", "retriever", {"plan_json": "Plan to execute"}),
            ("retriever", "extractor", {"documents_json": "Raw documents"}),
            ("extractor", "classifier", {"candidates_json": "Signal candidates"}),
            ("classifier", "critic", {"classified_json": "Classified signals"}),
            ("critic", "survivor", {"critique_json": "Critique decisions"}),
            ("survivor", "analyst", {"surviving_signals_json": "Signals surviving the critic"}),
            ("analyst", "persistence", {"brief_md": "Markdown brief"}),
            ("persistence", "EXIT", {"signals_kept": "Count kept", "signals_inserted": "Count inserted"}),
        ],
    )
    return g
