"""Tests for the multi-agent debate Critic (Du et al. 2023).

Covers:
  - env gate (MASF_CRITIC_DEBATE_ROUNDS clamping)
  - debate snapshot forwards (overwriting pre-debate snapshots)
  - chain helpers (node count + edge endpoints)
  - graph-level integration: all three modes (single / consensus / debate)
    must build successfully end-to-end
"""

from __future__ import annotations

import pytest

from masfactory_system.agents import critic_debate as cd


# ---------- env gate ----------

def test_debate_rounds_default_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_CRITIC_DEBATE_ROUNDS", raising=False)
    assert cd.debate_rounds() == 0


@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("-1", 0), ("", 0), ("garbage", 0),
    ("1", 1), ("2", 1), ("10", 1),  # any positive value clamps to 1
])
def test_debate_rounds_clamps_to_zero_or_one(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    monkeypatch.setenv("MASF_CRITIC_DEBATE_ROUNDS", raw)
    assert cd.debate_rounds() == expected


# ---------- snapshot forwards ----------

def test_debate_snapshots_overwrite_pass_specific_key() -> None:
    """The whole point of debate-snap-N is to OVERWRITE the pre-debate
    snapshot at critique_pass_N_json — without that, the vote node would
    still see the pre-debate verdicts."""
    pre_debate = '{"decisions": [{"signal_index": 0, "keep": true, "reason": "first pass"}]}'
    post_debate = '{"decisions": [{"signal_index": 0, "keep": false, "reason": "revised after debate"}]}'

    for pass_num, forward in (
        (1, cd.debate_snapshot_1_forward),
        (2, cd.debate_snapshot_2_forward),
        (3, cd.debate_snapshot_3_forward),
    ):
        attrs = {
            f"critique_pass_{pass_num}_json": pre_debate,  # pre-existing
            "critique_json": post_debate,                   # debate agent's revision
        }
        out = forward(None, attrs)
        # Overwrites the pre-debate snapshot with the debate output
        assert out[f"critique_pass_{pass_num}_json"] == post_debate
        # Clears critique_json so the next debate agent starts fresh
        assert out["critique_json"] == ""


def test_debate_snapshot_handles_missing_critique_json() -> None:
    """A debate Agent that failed mid-call leaves critique_json empty;
    the snapshot writes empty (NOT raises) so the chain continues."""
    out = cd.debate_snapshot_1_forward(None, {})
    assert out["critique_pass_1_json"] == ""


# ---------- chain helpers ----------

def test_debate_chain_nodes_has_six_steps() -> None:
    """3 debate agents + 3 debate snapshots = 6 nodes."""
    nodes = list(cd.debate_chain_nodes())
    names = [n for n, _ in nodes]
    assert names == [
        "debate-1", "debate-snap-1",
        "debate-2", "debate-snap-2",
        "debate-3", "debate-snap-3",
    ]


def test_debate_chain_edges_starts_at_snapshot_3() -> None:
    """The first edge should hook into the consensus chain's tail
    (snapshot-3) and pull all three critique_pass_N_json keys as
    debate context — without those the agents have nothing to debate over."""
    edges = list(cd.debate_chain_edges())
    src, dst, payload = edges[0]
    assert src == "snapshot-3"
    assert dst == "debate-1"
    for k in ("classified_json", "critique_pass_1_json",
              "critique_pass_2_json", "critique_pass_3_json"):
        assert k in payload


def test_debate_chain_edges_does_not_include_vote_bridge() -> None:
    """The 'debate-snap-3 → critic-vote' bridge is added by graph.py, not
    by this module — keeps the module from depending on the vote node
    name and lets graph.py compose multiple debate rounds in future."""
    edges = list(cd.debate_chain_edges())
    last_src, last_dst, _ = edges[-1]
    assert last_src == "debate-3"
    assert last_dst == "debate-snap-3"
    # No critic-vote anywhere in the module's own edges
    for src, dst, _ in edges:
        assert dst != "critic-vote"


# ---------- graph-level integration: all three modes build ----------

# v0.4.23 bumped every chain by 1 because the reranker-prefilter
# CustomNode is ALWAYS inserted between classifier and the critic
# (pass-through when MASF_RERANKER=0). Counts here are
# baseline-critic-nodes + 1.
@pytest.mark.parametrize("consensus,debate,expected_critic_nodes,mode_label", [
    (None, None, 2, "Mode A (single-pass)"),
    ("3", None, 8, "Mode B (consensus only)"),  # 1 reranker + 3 passes + 3 snapshots + 1 vote
    ("3", "1", 14, "Mode C (consensus + debate)"),  # 8 + 6 debate
    # Debate without consensus → silently ignored (Mode A)
    (None, "1", 2, "debate-without-consensus collapses to Mode A"),
    # Consensus + debate=0 → Mode B
    ("3", "0", 8, "explicit debate=0 stays Mode B"),
])
def test_graph_builds_in_all_modes(
    monkeypatch: pytest.MonkeyPatch,
    consensus: str | None,
    debate: str | None,
    expected_critic_nodes: int,
    mode_label: str,
) -> None:
    """End-to-end: every combination of consensus + debate env vars should
    produce a graph that compiles. The number of critic-chain nodes is the
    cheapest invariant to check across modes."""
    import importlib
    import sys

    from masfactory import Agent, template_defaults_for

    if consensus is None:
        monkeypatch.delenv("MASF_CRITIC_CONSENSUS_PASSES", raising=False)
    else:
        monkeypatch.setenv("MASF_CRITIC_CONSENSUS_PASSES", consensus)
    if debate is None:
        monkeypatch.delenv("MASF_CRITIC_DEBATE_ROUNDS", raising=False)
    else:
        monkeypatch.setenv("MASF_CRITIC_DEBATE_ROUNDS", debate)

    sys.modules.pop("masfactory_system.graph", None)
    graph_mod = importlib.import_module("masfactory_system.graph")

    from masfactory_system.runner import _StubModel
    with template_defaults_for(type_filter=Agent, model=_StubModel()):
        graph = graph_mod.build_graph()
        graph.build()

    assert len(graph_mod._critic_nodes) == expected_critic_nodes, (
        f"{mode_label}: expected {expected_critic_nodes} critic-chain nodes, "
        f"got {len(graph_mod._critic_nodes)}"
    )


def test_debate_mode_splices_edges_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    """In Mode C, the consensus chain's snapshot-3 → critic-vote edge is
    replaced by snapshot-3 → debate-1 ... debate-snap-3 → critic-vote.
    Verify the splicing by inspecting the edge list."""
    import importlib
    import sys

    monkeypatch.setenv("MASF_CRITIC_CONSENSUS_PASSES", "3")
    monkeypatch.setenv("MASF_CRITIC_DEBATE_ROUNDS", "1")
    sys.modules.pop("masfactory_system.graph", None)
    graph_mod = importlib.import_module("masfactory_system.graph")

    edges = graph_mod._critic_edges
    # No direct snapshot-3 → critic-vote edge in debate mode
    for src, dst, _ in edges:
        assert not (src == "snapshot-3" and dst == "critic-vote"), (
            "Mode C must replace snapshot-3 → critic-vote with the debate chain"
        )
    # snapshot-3 should now connect to debate-1
    snap3_targets = [dst for src, dst, _ in edges if src == "snapshot-3"]
    assert "debate-1" in snap3_targets

    # debate-snap-3 should connect to critic-vote (the bridge graph.py adds)
    bridge_sources = [src for src, dst, _ in edges if dst == "critic-vote"]
    assert "debate-snap-3" in bridge_sources

    # critic-vote → accumulate-actor preserved unchanged
    vote_targets = [dst for src, dst, _ in edges if src == "critic-vote"]
    assert "accumulate-actor" in vote_targets


def test_consensus_mode_keeps_direct_snapshot3_to_vote_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity check: Mode B (consensus, no debate) must keep snapshot-3 →
    critic-vote direct, not route through the debate chain."""
    import importlib
    import sys

    monkeypatch.setenv("MASF_CRITIC_CONSENSUS_PASSES", "3")
    monkeypatch.delenv("MASF_CRITIC_DEBATE_ROUNDS", raising=False)
    sys.modules.pop("masfactory_system.graph", None)
    graph_mod = importlib.import_module("masfactory_system.graph")

    edges = graph_mod._critic_edges
    direct = any(src == "snapshot-3" and dst == "critic-vote" for src, dst, _ in edges)
    assert direct, "Mode B must keep snapshot-3 → critic-vote direct"
    # And no debate nodes anywhere
    debate_nodes = [n for n, _ in graph_mod._critic_nodes if "debate" in n]
    assert debate_nodes == []
