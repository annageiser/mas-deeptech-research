"""Tests for the consensus-critic helpers (env gate, vote logic, parse robustness).

The graph-level wiring is exercised by test_graph_builds.py (which builds
the RootGraph end-to-end in both modes). Here we cover the pure-Python
logic in critic_consensus.py without needing MASFactory or a live LLM.
"""

from __future__ import annotations

import json

import pytest

from masfactory_system.agents import critic_consensus as cc


# ---------- env gate ----------

def test_consensus_passes_default_is_single_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_CRITIC_CONSENSUS_PASSES", raising=False)
    assert cc.consensus_passes() == 1


@pytest.mark.parametrize("raw,expected", [
    ("0", 1), ("1", 1), ("", 1), ("garbage", 1),  # falsy / <=1 → single pass
    ("2", 3), ("3", 3), ("7", 3),  # any N>1 → clamped to 3
])
def test_consensus_passes_clamps(monkeypatch: pytest.MonkeyPatch, raw: str, expected: int) -> None:
    monkeypatch.setenv("MASF_CRITIC_CONSENSUS_PASSES", raw)
    assert cc.consensus_passes() == expected


# ---------- pass parsing ----------

def test_parse_pass_accepts_decisions_array() -> None:
    raw = json.dumps({"decisions": [
        {"signal_index": 0, "keep": True, "reason": "looks good"},
        {"signal_index": 1, "keep": False, "reason": "boilerplate"},
    ]})
    out = cc._parse_pass(raw)
    assert len(out) == 2
    assert out[0]["keep"] is True
    assert out[1]["keep"] is False


def test_parse_pass_handles_fenced_and_tagged() -> None:
    """Tolerate the LLM wrapping output in code fences or tagged-field XML."""
    payload = json.dumps({"decisions": [{"signal_index": 0, "keep": True}]})
    for raw in (
        f"```json\n{payload}\n```",
        f"<critique_json>{payload}</critique_json>",
        f"```\n<critique_json>{payload}</critique_json>\n```",
    ):
        out = cc._parse_pass(raw)
        assert len(out) == 1, f"failed for raw={raw[:60]}"


def test_parse_pass_handles_alternate_key_names() -> None:
    for key in ("decisions", "keep_signals", "results", "verdicts"):
        raw = json.dumps({key: [{"signal_index": 0, "keep": True}]})
        out = cc._parse_pass(raw)
        assert len(out) == 1, f"failed for key={key}"


def test_parse_pass_handles_bare_list() -> None:
    raw = json.dumps([{"signal_index": 0, "keep": True}])
    out = cc._parse_pass(raw)
    assert len(out) == 1


def test_parse_pass_returns_empty_for_garbage() -> None:
    assert cc._parse_pass("") == []
    assert cc._parse_pass("not json") == []
    assert cc._parse_pass(json.dumps({"unrelated": "shape"})) == []


# ---------- vote logic ----------

def _pass(*decisions: tuple[int, bool, str]) -> str:
    """Helper: build a JSON pass output."""
    return json.dumps({
        "decisions": [
            {"signal_index": idx, "keep": keep, "reason": reason}
            for idx, keep, reason in decisions
        ]
    })


def test_vote_majority_keeps_when_two_of_three_say_keep() -> None:
    attrs = {
        "critique_pass_1_json": _pass((0, True, "good")),
        "critique_pass_2_json": _pass((0, True, "good")),
        "critique_pass_3_json": _pass((0, False, "boilerplate")),
    }
    out = cc._vote(None, attrs)
    decisions = json.loads(out["critique_json"])["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["signal_index"] == 0
    assert decisions[0]["keep"] is True
    audit = out["critic_consensus_audit"]
    assert audit["passes_effective"] == 3
    assert audit["threshold"] == 2
    assert audit["n_kept"] == 1
    assert audit["n_dropped"] == 0


def test_vote_majority_drops_when_two_of_three_say_drop() -> None:
    attrs = {
        "critique_pass_1_json": _pass((0, False, "low confidence")),
        "critique_pass_2_json": _pass((0, False, "low confidence")),
        "critique_pass_3_json": _pass((0, True, "borderline")),
    }
    out = cc._vote(None, attrs)
    decisions = json.loads(out["critique_json"])["decisions"]
    assert decisions[0]["keep"] is False
    assert out["critic_consensus_audit"]["n_dropped"] == 1


def test_vote_handles_signal_missing_from_some_passes() -> None:
    """If only 1 of 3 passes mentions a signal at all, the signal got 1 keep
    vote out of 3 effective passes — that's below the threshold (2), so drop."""
    attrs = {
        "critique_pass_1_json": _pass((0, True, "yes"), (1, True, "yes")),
        "critique_pass_2_json": _pass((0, True, "yes")),  # didn't mention #1
        "critique_pass_3_json": _pass((0, True, "yes")),  # didn't mention #1
    }
    out = cc._vote(None, attrs)
    decisions = {d["signal_index"]: d for d in json.loads(out["critique_json"])["decisions"]}
    assert decisions[0]["keep"] is True   # 3/3 keep
    assert decisions[1]["keep"] is False  # only 1/3 vote → drop


def test_vote_handles_one_pass_failing() -> None:
    """If one of three passes produces unparseable output, the vote still
    proceeds with the remaining two — threshold drops to 2 (majority of 2)."""
    attrs = {
        "critique_pass_1_json": _pass((0, True, "good")),
        "critique_pass_2_json": _pass((0, True, "good")),
        "critique_pass_3_json": "broken-non-json",
    }
    out = cc._vote(None, attrs)
    decisions = json.loads(out["critique_json"])["decisions"]
    assert decisions[0]["keep"] is True
    assert out["critic_consensus_audit"]["passes_effective"] == 2
    assert out["critic_consensus_audit"]["threshold"] == 2


def test_vote_with_all_passes_failing_returns_empty_decisions() -> None:
    """All three passes broken → empty decisions. AccumulateActor's
    fallback (no critique → keep everything) takes over, which is the
    correct recall-over-precision behaviour."""
    attrs = {
        "critique_pass_1_json": "",
        "critique_pass_2_json": "garbage",
        "critique_pass_3_json": None,
    }
    out = cc._vote(None, attrs)
    decisions = json.loads(out["critique_json"])["decisions"]
    assert decisions == []


def test_vote_includes_per_pass_reasons_in_audit() -> None:
    attrs = {
        "critique_pass_1_json": _pass((0, True, "novel result from arxiv")),
        "critique_pass_2_json": _pass((0, True, "concrete number cited")),
        "critique_pass_3_json": _pass((0, False, "could be paraphrased boilerplate")),
    }
    out = cc._vote(None, attrs)
    decisions = json.loads(out["critique_json"])["decisions"]
    reason = decisions[0]["reason"]
    assert "consensus:" in reason
    assert "novel result from arxiv" in reason
    assert "could be paraphrased boilerplate" in reason


# ---------- snapshot CustomNode behaviour ----------

def test_snapshot_moves_critique_json_to_pass_specific_key() -> None:
    """Snapshot N should copy critique_json → critique_pass_{N}_json and clear
    critique_json so the next pass's Agent starts from an empty slate."""
    attrs = {"critique_json": '{"decisions": [{"signal_index": 0, "keep": true}]}'}
    for pass_num, forward in (
        (1, cc.snapshot_pass_1_forward),
        (2, cc.snapshot_pass_2_forward),
        (3, cc.snapshot_pass_3_forward),
    ):
        out = forward(None, attrs)
        assert out[f"critique_pass_{pass_num}_json"] == attrs["critique_json"]
        assert out["critique_json"] == ""


def test_snapshot_handles_missing_critique_json() -> None:
    """If the Critic Agent failed to produce output, critique_json may be
    missing or empty. Snapshot should write an empty string rather than crash."""
    out = cc.snapshot_pass_1_forward(None, {})
    assert out["critique_pass_1_json"] == ""
    out = cc.snapshot_pass_2_forward(None, {"critique_json": None})
    assert out["critique_pass_2_json"] == ""


# ---------- chain helpers ----------

def test_consensus_chain_nodes_has_seven_steps() -> None:
    """3 critic passes + 3 snapshots + 1 vote = 7 nodes."""
    nodes = list(cc.consensus_chain_nodes())
    names = [n for n, _ in nodes]
    assert names == [
        "critic-pass-1", "snapshot-1",
        "critic-pass-2", "snapshot-2",
        "critic-pass-3", "snapshot-3",
        "critic-vote",
    ]


def test_consensus_chain_edges_connects_classifier_to_accumulator() -> None:
    edges = list(cc.consensus_chain_edges(from_node="classifier", to_node="accumulate-actor"))
    # First edge: classifier → critic-pass-1
    assert edges[0][0] == "classifier"
    assert edges[0][1] == "critic-pass-1"
    # Last edge: critic-vote → accumulate-actor (with critique_json payload)
    assert edges[-1][0] == "critic-vote"
    assert edges[-1][1] == "accumulate-actor"
    assert "critique_json" in edges[-1][2]


def test_graph_builds_in_consensus_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: with the env flag set, importing the graph module
    cleanly produces a RootGraph that includes all consensus nodes.

    Forces a fresh import of `graph` so the env var is re-read at module-
    load time (the chain selection happens at import, not per-invocation —
    a deliberate choice so the graph topology is fixed for the run)."""
    import importlib
    import sys

    from masfactory import Agent, template_defaults_for

    monkeypatch.setenv("MASF_CRITIC_CONSENSUS_PASSES", "3")
    # Drop the cached module so the env-gated chain selection re-runs.
    sys.modules.pop("masfactory_system.graph", None)
    graph_mod = importlib.import_module("masfactory_system.graph")

    from masfactory_system.runner import _StubModel
    with template_defaults_for(type_filter=Agent, model=_StubModel()):
        graph = graph_mod.build_graph()
        graph.build()

    # The graph's nested Loop should now have 7 critic-chain nodes inside
    # (vs. 1 in single-pass mode). Confirm by interrogating the loop's nodes.
    loop_node_template = None
    for name, tpl in [
        ("planner", None), ("retriever", None), ("actor-loop", None),
    ]:
        # The actor-loop NodeTemplate is held on the module, easier to grab there:
        if hasattr(graph_mod, "ActorLoopNode"):
            loop_node_template = graph_mod.ActorLoopNode
            break

    assert loop_node_template is not None
    # NodeTemplate stores kwargs in a private dict; the public way is to
    # check the rebuilt _critic_nodes module-level variable.
    assert len(graph_mod._critic_nodes) == 7  # 3 passes + 3 snapshots + 1 vote


def test_graph_builds_in_single_pass_mode_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default mode: 1 critic node, no consensus chain."""
    import importlib
    import sys

    monkeypatch.delenv("MASF_CRITIC_CONSENSUS_PASSES", raising=False)
    sys.modules.pop("masfactory_system.graph", None)
    graph_mod = importlib.import_module("masfactory_system.graph")
    assert len(graph_mod._critic_nodes) == 1
