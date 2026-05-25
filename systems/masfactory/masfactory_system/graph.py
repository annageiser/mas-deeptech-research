"""RootGraph wiring for System A.

  ENTRY → Planner → Retriever → ActorLoop(Extractor → Classifier → Critic
                                          → AccumulateActor)
                              → Analyst → Persistence → EXIT

The per-actor Loop is the key architectural improvement over a single-pass
graph. Each loop iteration sees ONE actor's documents in isolation, which:
  - eliminates cross-actor attribution drift (the dominant failure mode
    when 40 actors' documents are fed into one Extractor prompt)
  - keeps each LLM prompt small enough for free-tier Nemotron's effective
    context window
  - lets the Critic and Classifier focus on a single actor's signal mix
  - lets a single hung actor not block others (the failover wrapper +
    90 s timeout cap individual call cost)

Pattern is the one MASFactory uses in its `applications/nowwhat/` reference
app (each paper batch processed in its own Loop iteration).

The deprecated linear-flow Survivor node is kept exported for any external
imports but no longer wired into the graph — AccumulateActor performs the
same filtering per iteration, and the Analyst reads `surviving_signals_json`
(written by AccumulateActor each iteration with the run-wide accumulator).

Sources the Retriever can pull per actor:
  - "arxiv"   — papers from export.arxiv.org/api/query
  - "website" — homepage + RSS feeds + newsy subpages (depth 2)
  - "news"    — third-party coverage via Google News RSS (Switzerland-biased,
                Kolbe & Burnett 1991 content-analysis frame)

The model is bound to all Agent nodes at runtime via
`template_defaults_for(type_filter=Agent, model=...)` — see `runner.py`.
"""

from __future__ import annotations

from masfactory import Loop, NodeTemplate, RootGraph

from .agents import (
    AccumulateActorNode,
    AnalystNode,
    ClassifierNode,
    CriticNode,
    ExtractorNode,
    PersistenceNode,
    PlannerNode,
    PrepareCurrentActorNode,
    RetrieverNode,
    actor_loop_done,
)


WORKFLOW_ATTRIBUTES: dict[str, object] = {
    # ---- injected by runner ----
    "actor_pool": [],
    "limit_actors": 3,
    "limit_arxiv_per_actor": 5,
    "limit_website_pages_per_actor": 3,
    "limit_news_per_actor": 5,
    "web_cache_dir": "/data/raw/web_cache",
    "store": None,
    "audit_folder": None,
    "run_id": None,
    "config_snapshot": {},
    # ---- flows between nodes (whole-run scope) ----
    "candidate_actors_json": "",
    "plan_json": "",
    "documents": [],
    "documents_count": 0,
    "documents_json": "",
    "documents_by_actor": [],
    "documents_by_actor_count": 0,
    "actor_loop_index": 0,
    # ---- per-iteration scratch (cleared by PrepareCurrentActor each loop) ----
    "current_actor_slug": "",
    "current_actor_doc_count": 0,
    "candidates_json": "",
    "classified_json": "",
    "critique_json": "",
    # ---- run-wide accumulators (written by AccumulateActor each iteration) ----
    "all_classified": [],
    "all_critique": [],
    "all_surviving_signals": [],
    "dropped_cross_actor": [],
    # ---- after-loop ----
    "surviving_signals_json": "",
    "brief_md": "",
    "signals_kept": 0,
    "signals_inserted": 0,
    "retriever_errors": [],
}


ActorLoopNode = NodeTemplate(
    Loop,
    max_iterations=500,
    terminate_condition_function=actor_loop_done,
    pull_keys={
        "documents_by_actor": "Grouped per-actor documents from Retriever",
        "actor_loop_index": "Index of the next actor to process",
        "all_classified": "Accumulated classified signals (mutated by AccumulateActor)",
        "all_critique": "Accumulated critique decisions",
        "all_surviving_signals": "Accumulated surviving signals",
        "dropped_cross_actor": "Cross-actor attribution drops",
        # MASFactory's Loop requires a key to be in pull_keys for it to be
        # tracked and pushed back out — even when only the inner accumulator
        # populates it. Default = empty string.
        "surviving_signals_json": "Run-wide surviving signals as JSON (for Analyst)",
    },
    push_keys={
        "all_classified": "...",
        "all_critique": "...",
        "all_surviving_signals": "...",
        "dropped_cross_actor": "...",
        "actor_loop_index": "...",
        "surviving_signals_json": "Run-wide surviving signals as JSON (for Analyst)",
    },
    attributes={
        # Per-iteration scratch defaults — overwritten each iteration.
        "current_actor_slug": "",
        "current_actor_doc_count": 0,
        "documents_json": "[]",
        "candidates_json": "",
        "classified_json": "",
        "critique_json": "",
    },
    nodes=[
        ("prepare-actor", PrepareCurrentActorNode),
        ("extractor", ExtractorNode),
        ("classifier", ClassifierNode),
        ("critic", CriticNode),
        ("accumulate-actor", AccumulateActorNode),
    ],
    edges=[
        ("controller", "prepare-actor", {}),
        ("prepare-actor", "extractor", {"documents_json": "Current actor's documents"}),
        ("extractor", "classifier", {"candidates_json": "Signal candidates"}),
        ("classifier", "critic", {"classified_json": "Classified signals"}),
        ("critic", "accumulate-actor", {"critique_json": "Critique decisions"}),
        ("accumulate-actor", "controller", {}),
    ],
)


def build_graph() -> RootGraph:
    g = RootGraph(
        name="masfactory_swiss_quantum",
        attributes=dict(WORKFLOW_ATTRIBUTES),
        nodes=[
            ("planner", PlannerNode),
            ("retriever", RetrieverNode),
            ("actor-loop", ActorLoopNode),
            ("analyst", AnalystNode),
            ("persistence", PersistenceNode),
        ],
        edges=[
            ("ENTRY", "planner", {"candidate_actors_json": "JSON list of candidate actors", "limit_actors": "Quota"}),
            ("planner", "retriever", {"plan_json": "Plan to execute"}),
            ("retriever", "actor-loop", {
                "documents_by_actor": "Per-actor document groups",
                "actor_loop_index": "Loop starting index",
            }),
            ("actor-loop", "analyst", {
                "surviving_signals_json": "Run-wide surviving signals",
            }),
            ("analyst", "persistence", {"brief_md": "Markdown brief"}),
            ("persistence", "EXIT", {"signals_kept": "Count kept", "signals_inserted": "Count inserted"}),
        ],
    )
    return g
