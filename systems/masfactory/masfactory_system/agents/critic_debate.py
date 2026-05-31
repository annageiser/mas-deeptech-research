"""Multi-agent debate Critic — Du et al. (2023) on top of the consensus chain.

Optional refinement of the self-consistency Critic in `critic_consensus.py`.
Gated by `MASF_CRITIC_DEBATE_ROUNDS` (default 0 = no debate, just consensus
vote). Implemented only for R=1; R=2 is feasible but Du et al. report
plateauing gains past one debate round on classification-style tasks, and
each round triples Critic LLM cost.

## Why this exists

Wang et al. (2023) self-consistency — already shipped in
`critic_consensus.py` — samples N independent Critics and majority-votes.
It strictly improves over a single greedy sample, but it leaves on the
table any information that would have shifted a Critic's vote *if it had
seen the others' arguments*.

Du, Li, Torralba, Tenenbaum, Mordatch (2023) — "Improving Factuality and
Reasoning in Language Models through Multiagent Debate" — formalise the
extension: N agents produce independent answers, then for R rounds each
agent sees the others' answers + reasoning and revises. The final answer
is voted over the *post-debate* set. They report factual-QA accuracy
lifts of 5-12 percentage points over both single-pass and N-pass-
without-debate baselines.

For the Critic, the relevant intuition is: a single Critic may flag a
signal as "boilerplate" without noticing that two other Critics found
concrete evidence in the *same* signal. Debate gives the first Critic a
chance to revise. Symmetrically: two Critics may both miss a duplicate
that the third spotted.

## Architecture (graph fragment, when enabled)

  consensus chain (pass-1 → snap-1 → ... → snap-3) — see critic_consensus.py
       ↓ critique_pass_1_json, critique_pass_2_json, critique_pass_3_json
  debate-1 (Agent: "You are Critic #1; here are all three verdicts; revise")
       ↓ critique_json (= debate-1's revised verdict)
  debate-snap-1 (CustomNode: critique_json → critique_pass_1_json, clear)
  debate-2 (Agent: "You are Critic #2; ...")
       ↓ critique_json
  debate-snap-2 (CustomNode: critique_json → critique_pass_2_json, clear)
  debate-3 (Agent: "You are Critic #3; ...")
       ↓ critique_json
  debate-snap-3 (CustomNode: critique_json → critique_pass_3_json, clear)
       ↓
  critic-vote (unchanged — reads the now-overwritten critique_pass_N_json)

Key design choice: the debate snapshots OVERWRITE `critique_pass_N_json`
so the existing `CriticVoteNode` works unchanged. This keeps the diff
small and the vote logic uniform across modes.

Per-agent identity is preserved via three distinct prompt templates,
each labelling its agent as "Critic #N" and pointing at the
`critique_pass_N_json` block as "your prior verdict". Without per-agent
prompts the three debate calls would be indistinguishable and the
debate would collapse back to self-consistency at higher cost.

## Cost

  - Baseline single-pass: 1× Critic call per actor.
  - Consensus (3-pass, no debate, current default when MASF_CRITIC_CONSENSUS_PASSES=3): 3×.
  - Consensus + R=1 debate (this module, MASF_CRITIC_DEBATE_ROUNDS=1): 6×.

Critic is ~10-15% of run total LLM cost, so R=1 debate adds 40-60% to
total tokens vs. baseline (or 25-40% vs. plain consensus). Default off;
turn on for evaluation runs that compare classification quality across
all three modes.

## Gating semantics

  MASF_CRITIC_DEBATE_ROUNDS unset / 0 / negative → no debate (vote over
    plain consensus snapshots; if MASF_CRITIC_CONSENSUS_PASSES is also 1
    this collapses to single-pass)
  MASF_CRITIC_DEBATE_ROUNDS >= 1 → debate enabled (only R=1 implemented;
    larger values are silently clamped to 1 to avoid surprise cost
    explosions if someone sets =10 by mistake)

Debate ALWAYS requires MASF_CRITIC_CONSENSUS_PASSES=3 as a prerequisite
(can't debate without prior verdicts to debate over) — graph.py enforces
this combination check.
"""

from __future__ import annotations

import os

from masfactory import (
    Agent,
    CustomNode,
    NodeTemplate,
    ParagraphMessageFormatter,
    TaggedFieldMessageFormatter,
)


# ---------- env gate ----------

def debate_rounds() -> int:
    """Read MASF_CRITIC_DEBATE_ROUNDS. Returns 0 (off) or 1 (one round)."""
    raw = os.environ.get("MASF_CRITIC_DEBATE_ROUNDS", "0")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    return 1  # only R=1 implemented; >1 clamped (see module docstring)


# ---------- debate prompts ----------

# Identical instructions for all three debate agents. The per-agent identity
# ("you are Critic #N") goes in the prompt template, not the instructions,
# because MASFactory's instructions are shared template-wide.
DEBATE_INSTRUCTIONS = """You are one of three Critics in a multi-agent debate \
about classified Swiss-quantum signals.

Three Critics already independently reviewed the same signals. Their verdicts \
appear below as <critic_1_verdict>, <critic_2_verdict>, <critic_3_verdict>. \
Your prior verdict is one of those three (the prompt will tell you which).

Reconsider your prior verdict in light of the others' reasoning:
- If both other Critics disagree with you on a signal, weigh their reasoning. \
They may have spotted boilerplate you missed or evidence you dismissed.
- If you remain convinced your original answer was correct, stand firm — \
debate is not majority-pressure; it's an opportunity to revise on new \
information.
- The vote at the end is over the FINAL (debated) verdicts, not the originals.

Same rules as the initial pass:
- Drop any signal with confidence < 0.4.
- Drop generic boilerplate ("leading provider", "we are committed to ...").
- Mark exact-meaning duplicates: keep the first, set keep=false and \
duplicate_of=<earlier_index> on the later ones.
- Be conservative — if in doubt, keep the signal. Recall over precision.

Return ONLY JSON.
"""


def _debate_prompt(pass_num: int) -> str:
    """The per-agent debate prompt template. Each debate agent gets a
    template that labels it as Critic #N and points at its prior verdict."""
    return (
        "<classified>{classified_json}</classified>\n\n"
        "<critic_1_verdict>{critique_pass_1_json}</critic_1_verdict>\n"
        "<critic_2_verdict>{critique_pass_2_json}</critic_2_verdict>\n"
        "<critic_3_verdict>{critique_pass_3_json}</critic_3_verdict>\n\n"
        f"You are Critic #{pass_num}. Your prior verdict is <critic_{pass_num}_verdict>. "
        "All three Critics will see this debate and revise in parallel.\n\n"
        "Now produce your REVISED verdict. Return JSON of shape:\n"
        "{{\n"
        '  "decisions": [\n'
        "    {{\n"
        '      "signal_index": 0,\n'
        '      "keep": true,\n'
        '      "reason": "...",\n'
        '      "duplicate_of": null\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    )


def _make_debate_agent(pass_num: int) -> NodeTemplate:
    """One debate Agent. Pulls classified_json + all three critique passes;
    pushes critique_json (which the snapshot then routes to the matching
    pass-specific key, overwriting the pre-debate snapshot)."""
    return NodeTemplate(
        Agent,
        instructions=DEBATE_INSTRUCTIONS,
        prompt_template=_debate_prompt(pass_num),
        pull_keys={
            "classified_json": "The classified signals being debated",
            "critique_pass_1_json": "Critic #1's prior verdict",
            "critique_pass_2_json": "Critic #2's prior verdict",
            "critique_pass_3_json": "Critic #3's prior verdict",
        },
        push_keys={"critique_json": f"Critic #{pass_num}'s revised verdict"},
        formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
    )


DebatePass1Node = _make_debate_agent(1)
DebatePass2Node = _make_debate_agent(2)
DebatePass3Node = _make_debate_agent(3)


# ---------- debate-snapshot forwards (identical shape to consensus snapshots,
# but kept as their own functions for clean test-time naming) ----------

def _debate_snapshot_forward(pass_num: int):
    """Move critique_json → critique_pass_{N}_json (overwriting the
    pre-debate snapshot). Clearing critique_json keeps the next debate
    Agent's prompt from accidentally including a prior agent's output."""
    pass_key = f"critique_pass_{pass_num}_json"

    def _forward(_input: dict, attrs: dict) -> dict:
        return {
            pass_key: attrs.get("critique_json", "") or "",
            "critique_json": "",
        }

    return _forward


debate_snapshot_1_forward = _debate_snapshot_forward(1)
debate_snapshot_2_forward = _debate_snapshot_forward(2)
debate_snapshot_3_forward = _debate_snapshot_forward(3)


def _make_debate_snapshot(forward) -> NodeTemplate:
    return NodeTemplate(CustomNode, forward=forward, pull_keys=None, push_keys=None)


DebateSnapshot1Node = _make_debate_snapshot(debate_snapshot_1_forward)
DebateSnapshot2Node = _make_debate_snapshot(debate_snapshot_2_forward)
DebateSnapshot3Node = _make_debate_snapshot(debate_snapshot_3_forward)


# ---------- chain builder ----------

def debate_chain_nodes():
    """The (name, NodeTemplate) pairs for the debate chain. Wire these
    AFTER the consensus chain's `snapshot-3` and BEFORE `critic-vote` to
    convert plain consensus into Du-style debate."""
    return [
        ("debate-1", DebatePass1Node),
        ("debate-snap-1", DebateSnapshot1Node),
        ("debate-2", DebatePass2Node),
        ("debate-snap-2", DebateSnapshot2Node),
        ("debate-3", DebatePass3Node),
        ("debate-snap-3", DebateSnapshot3Node),
    ]


def debate_chain_edges():
    """Edges for the debate chain. Connects 'snapshot-3' (the last consensus
    node) through the 6 debate nodes and out to 'critic-vote'.

    Each debate Agent pulls classified_json (unchanged) and the three
    pre-debate critique_pass_N_json snapshots (which together form the
    debate context). Each Agent's output is snapshot'd back to its own
    pass key, OVERWRITING the pre-debate snapshot — so the existing vote
    node reads the post-debate verdicts without any change to its logic.
    """
    return [
        ("snapshot-3", "debate-1", {
            "classified_json": "Signals under debate",
            "critique_pass_1_json": "Critic #1 prior verdict",
            "critique_pass_2_json": "Critic #2 prior verdict",
            "critique_pass_3_json": "Critic #3 prior verdict",
        }),
        ("debate-1", "debate-snap-1", {"critique_json": "Critic #1 revised"}),
        ("debate-snap-1", "debate-2", {
            # Each subsequent debate agent re-pulls the pass keys so it
            # sees the latest state (other agents' revisions visible too,
            # which is consistent with Du et al.'s 'shared blackboard' model).
            "classified_json": "Signals under debate",
            "critique_pass_1_json": "Critic #1 (revised)",
            "critique_pass_2_json": "Critic #2 prior verdict",
            "critique_pass_3_json": "Critic #3 prior verdict",
        }),
        ("debate-2", "debate-snap-2", {"critique_json": "Critic #2 revised"}),
        ("debate-snap-2", "debate-3", {
            "classified_json": "Signals under debate",
            "critique_pass_1_json": "Critic #1 (revised)",
            "critique_pass_2_json": "Critic #2 (revised)",
            "critique_pass_3_json": "Critic #3 prior verdict",
        }),
        ("debate-3", "debate-snap-3", {"critique_json": "Critic #3 revised"}),
        # The next edge ('debate-snap-3' → 'critic-vote') is added by
        # graph.py's `_build_critic_chain` because the destination is fixed
        # by the consensus chain, not by this module.
    ]
