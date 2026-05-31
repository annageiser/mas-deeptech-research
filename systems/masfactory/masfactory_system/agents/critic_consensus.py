"""Consensus Critic — N independent Critic passes + majority vote.

Optional alternative to the single-pass `CriticNode` in `critic.py`. Gated by
`MASF_CRITIC_CONSENSUS_PASSES` (default 1 = current single-pass behaviour;
set to 3 to enable self-consistency).

## Why this exists

Wang et al. (2023) — "Self-Consistency Improves Chain of Thought Reasoning
in Language Models" — show that sampling an LLM N times under temperature
> 0 and majority-voting the answers strictly improves over greedy decoding
for tasks where the correct answer is consistent but the model's first
sample is noisy. The Critic's job here ("drop low-confidence / boilerplate
signals, mark duplicates") is exactly that kind of task: the answer is
consistent across most samples, but a single sample may be over- or
under-aggressive on any given signal. Voting across 3 passes converges on
the consensus decision.

This is the simplest non-trivial deliberation pattern: independent samples
with no inter-pass debate. A richer variant (Du et al. 2023 multi-agent
debate, where each critic sees the others' arguments and revises) is
deliberately out of scope — it would add inter-pass coupling that obscures
which pass made which decision in the audit log.

## Architecture (graph fragment, when enabled)

  classifier
      ↓ classified_json
  critic-pass-1 (Agent — writes critique_json)
      ↓ critique_json
  snapshot-1 (CustomNode — moves critique_json → critique_pass_1_json, clears critique_json)
      ↓ classified_json (still in attrs, untouched)
  critic-pass-2 (Agent — writes critique_json)
      ↓ critique_json
  snapshot-2 (CustomNode — moves to critique_pass_2_json)
      ↓
  critic-pass-3 (Agent — writes critique_json)
      ↓ critique_json
  snapshot-3 (CustomNode — moves to critique_pass_3_json)
      ↓
  critic-vote (CustomNode — majority-vote, writes final critique_json)
      ↓ critique_json
  accumulate-actor

Each pass uses the identical instructions + prompt as the single-pass
`CriticNode`, so the comparison between single-pass and consensus is a
clean A/B over the temperature dimension. The model's default chat
temperature (1.0) gives variability between passes; if a deployment runs
deterministic decoding (temperature=0) the three passes degenerate to
one and the vote returns the same answer — safe degraded mode.

## Trade-off

Triples the Critic's LLM cost per actor. Critic is ~10-15% of total LLM
cost in a typical run, so consensus mode adds ~20-30% to total tokens.
Default off; turn on for evaluation runs that compare classification
quality with and without consensus.
"""

from __future__ import annotations

import json
import os
from typing import Iterable

from masfactory import (
    Agent,
    CustomNode,
    NodeTemplate,
    ParagraphMessageFormatter,
    TaggedFieldMessageFormatter,
)

from .critic import CRITIC_INSTRUCTIONS, CRITIC_PROMPT


# ---------- env-gate helpers ----------

def consensus_passes() -> int:
    """Read MASF_CRITIC_CONSENSUS_PASSES from the environment.

    Values <= 1 → single-pass (use original CriticNode).
    Values >= 3 → 3-pass consensus (we cap at 3; more passes would add cost
    without clear quality benefit per Wang et al. 2023's Figure 2 — gains
    plateau at N=3 for problems with binary-ish answers like keep/drop).
    The exact integer between 2 and 3 currently rounds up to 3.
    """
    raw = os.environ.get("MASF_CRITIC_CONSENSUS_PASSES", "1")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 1
    if n <= 1:
        return 1
    return 3  # 2 → 3 (need an odd N for clean majority); 4+ → 3 (diminishing returns)


# ---------- the three Critic Agents ----------

def _make_pass_node() -> NodeTemplate:
    """One Critic Agent — same prompt + push key as the single-pass version.
    The snapshot node after each pass moves the result to a pass-specific key."""
    return NodeTemplate(
        Agent,
        instructions=CRITIC_INSTRUCTIONS,
        prompt_template=CRITIC_PROMPT,
        pull_keys={"classified_json": "Classified signals (same input every pass)"},
        push_keys={"critique_json": "This pass's keep/drop decisions"},
        formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
    )


CriticPass1Node = _make_pass_node()
CriticPass2Node = _make_pass_node()
CriticPass3Node = _make_pass_node()


# ---------- the three Snapshot CustomNodes ----------

def _snapshot_forward(pass_num: int):
    """Build the snapshot forward function for pass N.

    Exposed at module level (rather than nested inside _make_snapshot) so
    tests can call the forward directly without poking at NodeTemplate
    internals. The NodeTemplate-construction layer below just wraps these."""
    pass_key = f"critique_pass_{pass_num}_json"

    def _forward(_input: dict, attrs: dict) -> dict:
        return {
            pass_key: attrs.get("critique_json", "") or "",
            "critique_json": "",  # clear for the next pass
        }

    return _forward


snapshot_pass_1_forward = _snapshot_forward(1)
snapshot_pass_2_forward = _snapshot_forward(2)
snapshot_pass_3_forward = _snapshot_forward(3)


def _make_snapshot(forward) -> NodeTemplate:
    """Wrap a snapshot forward function as a MASFactory CustomNode template."""
    return NodeTemplate(CustomNode, forward=forward, pull_keys=None, push_keys=None)


CriticSnapshot1Node = _make_snapshot(snapshot_pass_1_forward)
CriticSnapshot2Node = _make_snapshot(snapshot_pass_2_forward)
CriticSnapshot3Node = _make_snapshot(snapshot_pass_3_forward)


# ---------- the vote node ----------

def _strip_fences_and_tag(raw: str, tag: str = "critique_json") -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    close, opn = f"</{tag}>", f"<{tag}>"
    if close in text:
        text = text.split(close)[0]
    if opn in text:
        text = text.split(opn)[1]
    return text.strip()


def _parse_pass(raw: str) -> list[dict]:
    """Parse one pass's JSON output into a list of decision dicts.

    Defensive against the LLM occasionally returning a list directly or an
    object with `decisions` either spelled `keep_signals` or with the array
    nested one layer deeper. Returns [] for unparseable output — that pass
    simply doesn't contribute to the vote, which is the right behaviour
    when one of three samples failed (the other two carry the vote).
    """
    if not raw:
        return []
    text = _strip_fences_and_tag(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("decisions", "keep_signals", "results", "verdicts"):
            v = obj.get(key)
            if isinstance(v, list):
                return v
    return []


def _vote(_input: dict, attrs: dict) -> dict:
    """Majority-vote across the three pass results.

    For each signal_index that appears in any pass:
      - keep = True if a strict majority of passes voted keep=True
      - reason = "consensus: K/N kept | <first reason><br>..."
    Duplicates are intentionally ignored in the vote — the Critic's
    `duplicate_of` field is a hint, not a hard constraint, and the
    downstream AccumulateActor + Persistence layers already dedup on
    (actor_slug, source_url, content_hash).
    """
    pass_keys = ("critique_pass_1_json", "critique_pass_2_json", "critique_pass_3_json")
    passes: list[list[dict]] = [_parse_pass(attrs.get(k, "")) for k in pass_keys]

    # How many passes actually produced any decisions? (others were empty / failed)
    n_effective = sum(1 for p in passes if p)
    if n_effective == 0:
        # All three passes failed — return empty decisions (downstream defaults
        # to keep-all when critique is empty, which is the recall-over-
        # precision policy we want for the thesis).
        return {"critique_json": json.dumps({"decisions": []})}

    threshold = (n_effective // 2) + 1  # strict majority

    # Aggregate
    all_indices: set[int] = set()
    keep_votes: dict[int, int] = {}
    seen_votes: dict[int, int] = {}  # how many passes mentioned this index at all
    reasons: dict[int, list[str]] = {}
    for p in passes:
        for d in p:
            idx = d.get("signal_index")
            if not isinstance(idx, int):
                continue
            all_indices.add(idx)
            seen_votes[idx] = seen_votes.get(idx, 0) + 1
            if d.get("keep"):
                keep_votes[idx] = keep_votes.get(idx, 0) + 1
            r = d.get("reason")
            if isinstance(r, str) and r.strip():
                reasons.setdefault(idx, []).append(r.strip()[:120])

    decisions: list[dict] = []
    for idx in sorted(all_indices):
        votes = keep_votes.get(idx, 0)
        seen = seen_votes.get(idx, 0)
        keep = votes >= threshold
        reason_blob = (
            f"consensus: kept by {votes}/{n_effective} pass(es), "
            f"seen by {seen}/{n_effective}. "
            + " || ".join(reasons.get(idx, []))
        )
        decisions.append({
            "signal_index": idx,
            "keep": keep,
            "reason": reason_blob[:1500],
            "duplicate_of": None,
        })

    return {
        "critique_json": json.dumps({"decisions": decisions}),
        # Also stash the raw vote tally for audit so the thesis can show
        # disagreement rates between passes.
        "critic_consensus_audit": {
            "passes_effective": n_effective,
            "threshold": threshold,
            "n_signals_indexed": len(all_indices),
            "n_kept": sum(1 for d in decisions if d["keep"]),
            "n_dropped": sum(1 for d in decisions if not d["keep"]),
        },
    }


CriticVoteNode = NodeTemplate(CustomNode, forward=_vote, pull_keys=None, push_keys=None)


# ---------- public chain builder used by graph.py ----------

def consensus_chain_nodes() -> Iterable[tuple[str, NodeTemplate]]:
    """The (name, NodeTemplate) pairs for the consensus chain — wire these into
    the per-actor Loop in place of the single ("critic", CriticNode)."""
    return [
        ("critic-pass-1", CriticPass1Node),
        ("snapshot-1", CriticSnapshot1Node),
        ("critic-pass-2", CriticPass2Node),
        ("snapshot-2", CriticSnapshot2Node),
        ("critic-pass-3", CriticPass3Node),
        ("snapshot-3", CriticSnapshot3Node),
        ("critic-vote", CriticVoteNode),
    ]


def consensus_chain_edges(
    *, from_node: str = "classifier", to_node: str = "accumulate-actor"
) -> Iterable[tuple]:
    """The edges that wire the consensus chain between `from_node` and
    `to_node`. Each pair (Agent → Snapshot) carries `critique_json`; each
    pair (Snapshot → next Pass) doesn't need to forward anything explicitly
    because `classified_json` and the per-pass keys live in graph attributes
    and propagate automatically."""
    return [
        (from_node, "critic-pass-1", {"classified_json": "Input to all passes"}),
        ("critic-pass-1", "snapshot-1", {"critique_json": "Pass 1 raw output"}),
        ("snapshot-1", "critic-pass-2", {"classified_json": "Same input as pass 1"}),
        ("critic-pass-2", "snapshot-2", {"critique_json": "Pass 2 raw output"}),
        ("snapshot-2", "critic-pass-3", {"classified_json": "Same input as pass 1"}),
        ("critic-pass-3", "snapshot-3", {"critique_json": "Pass 3 raw output"}),
        ("snapshot-3", "critic-vote", {}),
        ("critic-vote", to_node, {"critique_json": "Voted final critique"}),
    ]
