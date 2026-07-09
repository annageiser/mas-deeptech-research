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
    RerankerPreFilterNode,
    RetrieverNode,
    actor_loop_done,
    consensus_chain_edges,
    consensus_chain_nodes,
    consensus_passes,
    debate_chain_edges,
    debate_chain_nodes,
    debate_rounds,
)


WORKFLOW_ATTRIBUTES: dict[str, object] = {
    # ---- injected by runner ----
    "actor_pool": [],
    "limit_actors": 3,
    "limit_arxiv_per_actor": 5,
    "limit_website_pages_per_actor": 3,
    "limit_news_per_actor": 5,
    # v0.5.0 — shared SearXNG substrate (empty URL → collector no-ops).
    "searxng_url": "",
    "limit_websearch_per_actor": 10,
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
    # Consensus-critic snapshots — populated only when consensus mode is on
    # (MASF_CRITIC_CONSENSUS_PASSES=3). Single-pass mode leaves these empty.
    "critique_pass_1_json": "",
    "critique_pass_2_json": "",
    "critique_pass_3_json": "",
    "critic_consensus_audit": {},
    # ---- run-wide accumulators (written by AccumulateActor each iteration) ----
    "all_classified": [],
    "all_critique": [],
    "all_surviving_signals": [],
    "dropped_cross_actor": [],
    # v0.4.23 — reranker pre-filter drops. Empty when MASF_RERANKER=0.
    "dropped_reranker": [],
    # ---- after-loop ----
    "surviving_signals_json": "",
    "brief_md": "",
    "signals_kept": 0,
    "signals_inserted": 0,
    "retriever_errors": [],
}


def _build_critic_chain() -> tuple[list, list]:
    """Return (loop_nodes_chunk, loop_edges_chunk) for the critic section of
    the per-actor Loop. Three modes, gated by env:

      Mode A (default): single-pass Critic.
        env: MASF_CRITIC_CONSENSUS_PASSES unset/=1, MASF_CRITIC_DEBATE_ROUNDS unset/=0

      Mode B: 3-pass consensus, no debate (Wang et al. 2023 self-consistency).
        env: MASF_CRITIC_CONSENSUS_PASSES=3, MASF_CRITIC_DEBATE_ROUNDS unset/=0

      Mode C: 3-pass consensus + 1 debate round (Du et al. 2023 multi-agent debate).
        env: MASF_CRITIC_CONSENSUS_PASSES=3 AND MASF_CRITIC_DEBATE_ROUNDS>=1

    Mode C requires Mode B as a prerequisite — debating requires prior
    verdicts to debate over. If MASF_CRITIC_DEBATE_ROUNDS is set without
    MASF_CRITIC_CONSENSUS_PASSES=3, the debate flag is silently ignored
    (logged at runner.py via config_snapshot if you need to detect it).

    v0.4.23: a `reranker-prefilter` CustomNode is ALWAYS inserted between
    `classifier` and whichever node consumes `classified_json` first. When
    MASF_RERANKER=0 (default) the node is a pure pass-through; when =1 it
    drops below-threshold candidates before the Critic sees them.
    """
    n_passes = consensus_passes()
    n_debate = debate_rounds() if n_passes > 1 else 0  # see prereq above

    # Common prefix: the rerank pre-filter sits between classifier and the
    # first critic-side node. Pass-through when disabled.
    prefix_nodes = [("reranker-prefilter", RerankerPreFilterNode)]
    prefix_edges = [
        ("classifier", "reranker-prefilter", {"classified_json": "Classified signals"}),
    ]

    if n_passes <= 1:
        # Mode A
        nodes = prefix_nodes + [("critic", CriticNode)]
        edges = prefix_edges + [
            ("reranker-prefilter", "critic", {"classified_json": "Re-ranked classified signals"}),
            ("critic", "accumulate-actor", {"critique_json": "Critique decisions"}),
        ]
        return nodes, edges

    # Mode B + maybe Mode C — consensus chain starts at reranker-prefilter
    # rather than classifier (one hop earlier).
    nodes = prefix_nodes + list(consensus_chain_nodes())
    edges = prefix_edges + list(consensus_chain_edges(
        from_node="reranker-prefilter", to_node="accumulate-actor",
    ))

    if n_debate >= 1:
        # Mode C: insert the debate chain between the last consensus snapshot
        # ('snapshot-3') and the vote ('critic-vote'). We:
        #   1) drop the consensus chain's snapshot-3 → critic-vote edge
        #   2) splice in the 6 debate nodes
        #   3) add the debate-snap-3 → critic-vote edge
        nodes = _splice_in_debate_nodes(nodes)
        edges = _splice_in_debate_edges(edges)

    return nodes, edges


def _splice_in_debate_nodes(consensus_nodes: list) -> list:
    """Insert the 6 debate nodes between 'snapshot-3' and 'critic-vote' in
    the consensus chain. Order matters: critic-vote must come last so its
    output flows to accumulate-actor."""
    out: list = []
    debate_nodes = list(debate_chain_nodes())
    for name, tpl in consensus_nodes:
        if name == "critic-vote":
            out.extend(debate_nodes)
        out.append((name, tpl))
    return out


def _splice_in_debate_edges(consensus_edges: list) -> list:
    """Rewrite the consensus chain's snapshot-3 → critic-vote edge to go
    through the debate chain instead. Add the debate-snap-3 → critic-vote
    bridge that critic_debate.py intentionally omits."""
    debate_edges = list(debate_chain_edges())
    bridge = [
        # Final hop from the last debate snapshot into the existing vote node.
        ("debate-snap-3", "critic-vote", {}),
    ]
    out: list = []
    for src, dst, payload in consensus_edges:
        if src == "snapshot-3" and dst == "critic-vote":
            # Replace with the debate chain + bridge.
            out.extend(debate_edges)
            out.extend(bridge)
        else:
            out.append((src, dst, payload))
    return out


_critic_nodes, _critic_edges = _build_critic_chain()


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
        # v0.4.23 — reranker drops accumulated across iterations.
        "dropped_reranker": "Reranker pre-filter drops",
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
        "dropped_reranker": "...",
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
        # Consensus-critic snapshots — present in both modes (cleared by
        # PrepareCurrentActor each iteration) so the Loop's attribute set
        # is consistent across single-pass and consensus runs.
        "critique_pass_1_json": "",
        "critique_pass_2_json": "",
        "critique_pass_3_json": "",
    },
    nodes=[
        ("prepare-actor", PrepareCurrentActorNode),
        ("extractor", ExtractorNode),
        ("classifier", ClassifierNode),
        *_critic_nodes,
        ("accumulate-actor", AccumulateActorNode),
    ],
    edges=[
        ("controller", "prepare-actor", {}),
        ("prepare-actor", "extractor", {"documents_json": "Current actor's documents"}),
        ("extractor", "classifier", {"candidates_json": "Signal candidates"}),
        *_critic_edges,
        # Loopback edge carries the keys we want exposed on the Loop's outer
        # output port — these flow through the controller into the implicit
        # terminate message that becomes the Loop node's output.
        ("accumulate-actor", "controller", {
            "surviving_signals_json": "Run-wide surviving signals as JSON",
            "all_classified": "Run-wide classified signals",
            "all_surviving_signals": "Run-wide surviving signals list",
            "all_critique": "Run-wide critique decisions",
            "dropped_cross_actor": "Cross-actor attribution drops",
            "dropped_reranker": "Reranker pre-filter drops",
            "actor_loop_index": "Next actor index",
        }),
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
