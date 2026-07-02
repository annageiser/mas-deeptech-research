"""Internal nodes for the per-actor processing Loop.

The Loop iterates once per actor in `documents_by_actor`. Each iteration:
  Controller → PrepareCurrentActor → Extractor → Classifier → Critic
            → AccumulateActor → Controller

`PrepareCurrentActor` picks the current actor's documents and exposes them
as `documents_json` (the key the Extractor pulls from). It also sets
`current_actor_slug` so the validation step in `AccumulateActor` can verify
no cross-actor attribution leaked.

`AccumulateActor` appends the loop iteration's classified + critique +
surviving signals to the run-wide accumulators, advances the loop index,
and clears the per-iteration scratch attributes so the next iteration starts
clean.

The Loop's terminate function (defined alongside the graph) checks
`actor_loop_index >= len(documents_by_actor)`.
"""

from __future__ import annotations

import json

from masfactory import CustomNode, NodeTemplate


# ---------- JSON helpers (mirrors persistence.py / survivor.py) ----------

def _strip_fences_and_tag(raw: str, tag: str | None = None) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    if tag:
        close, opn = f"</{tag}>", f"<{tag}>"
        if close in text:
            text = text.split(close)[0]
        if opn in text:
            text = text.split(opn)[1]
    return text.strip()


def _safe_json_load(raw: str, tag: str | None = None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(_strip_fences_and_tag(raw, tag))
    except json.JSONDecodeError:
        return {}


# ---------- PrepareCurrentActor ----------

def _prepare_current_actor(_input: dict, attrs: dict) -> dict:
    grouped = attrs.get("documents_by_actor") or []
    idx = int(attrs.get("actor_loop_index") or 0)

    if idx >= len(grouped):
        # Out of actors — should be unreachable because the Loop's terminate
        # condition runs first. Return empty so a stray invocation is harmless.
        return {
            "current_actor_slug": "",
            "documents_json": "[]",
            "current_actor_doc_count": 0,
        }

    actor_block = grouped[idx]
    docs = actor_block.get("documents") or []
    return {
        "current_actor_slug": actor_block.get("actor_slug", ""),
        "documents_json": json.dumps(docs),
        "current_actor_doc_count": len(docs),
        # Clear per-iteration scratch so it doesn't leak between actors.
        "candidates_json": "",
        "classified_json": "",
        "critique_json": "",
        # Consensus-critic snapshots (no-op when single-pass mode is in use,
        # but harmless to clear regardless).
        "critique_pass_1_json": "",
        "critique_pass_2_json": "",
        "critique_pass_3_json": "",
    }


PrepareCurrentActorNode = NodeTemplate(
    CustomNode, forward=_prepare_current_actor, pull_keys=None, push_keys=None
)


# ---------- AccumulateActor ----------

def _accumulate_actor(_input: dict, attrs: dict) -> dict:
    current_slug = attrs.get("current_actor_slug") or ""

    classified = _safe_json_load(attrs.get("classified_json", ""), tag="classified_json").get(
        "classified", []
    )
    critique = _safe_json_load(attrs.get("critique_json", ""), tag="critique_json").get(
        "decisions", []
    )

    # Defensive: drop any signal whose actor_slug doesn't match the current
    # iteration's actor. The per-actor Loop makes cross-attribution structurally
    # impossible at the input side; this catches LLM misattribution at the
    # output side too. Recorded for audit.
    #
    # v0.4.42: also recover from an upstream shape drift observed on Nemotron 3
    # Ultra 550B, where the Classifier occasionally emits individual signals as
    # JSON-encoded strings inside the classified list instead of parsed dicts.
    # Pre-v0.4.42 this crashed silently in Persistence with AttributeError; now
    # we JSON-decode strings back to dicts and drop anything else with a
    # diagnostic entry in the audit's dropped_upstream_shape.json.
    iteration_dropped: list[dict] = []
    filtered_classified: list[dict] = []
    keep_map: dict[int, int] = {}  # original index → new index
    for i, s in enumerate(classified):
        if not isinstance(s, dict):
            if isinstance(s, str):
                try:
                    maybe = json.loads(s)
                except (json.JSONDecodeError, TypeError):
                    maybe = None
                if isinstance(maybe, dict):
                    s = maybe
                else:
                    iteration_dropped.append({
                        "reason": "upstream shape: str not decodable to dict",
                        "type": type(maybe).__name__ if maybe is not None else "unparseable",
                        "content": s[:400],
                    })
                    continue
            else:
                iteration_dropped.append({
                    "reason": "upstream shape: non-dict, non-str",
                    "type": type(s).__name__,
                    "repr": repr(s)[:400],
                })
                continue
        if current_slug and s.get("actor_slug") != current_slug:
            iteration_dropped.append({
                "reason": "actor_slug mismatch (loop iteration)",
                "expected": current_slug,
                "got": s.get("actor_slug"),
                "signal": s,
            })
            continue
        keep_map[i] = len(filtered_classified)
        filtered_classified.append(s)

    # Re-index critique decisions to match the filtered classified list.
    filtered_critique: list[dict] = []
    for d in critique:
        old_idx = d.get("signal_index")
        if isinstance(old_idx, int) and old_idx in keep_map:
            new_d = dict(d)
            new_d["signal_index"] = keep_map[old_idx]
            filtered_critique.append(new_d)

    # Surviving = classified where Critic said keep=True (or, if Critic empty,
    # everything — recall over precision; matches the Survivor / Persistence
    # behaviour outside the loop).
    keep_indices = {d["signal_index"] for d in filtered_critique if d.get("keep")}
    if not filtered_critique:
        keep_indices = set(range(len(filtered_classified)))
    iter_surviving = [s for i, s in enumerate(filtered_classified) if i in keep_indices]

    # Append to the run-wide accumulators
    all_class = list(attrs.get("all_classified") or [])
    all_critique = list(attrs.get("all_critique") or [])
    all_surviving = list(attrs.get("all_surviving_signals") or [])
    cross_dropped = list(attrs.get("dropped_cross_actor") or [])

    offset = len(all_class)
    for d in filtered_critique:
        d2 = dict(d)
        if "signal_index" in d2 and isinstance(d2["signal_index"], int):
            d2["signal_index"] = d2["signal_index"] + offset
        all_critique.append(d2)
    all_class.extend(filtered_classified)
    all_surviving.extend(iter_surviving)
    cross_dropped.extend(iteration_dropped)

    return {
        "all_classified": all_class,
        "all_critique": all_critique,
        "all_surviving_signals": all_surviving,
        "dropped_cross_actor": cross_dropped,
        # v0.4.23: pass through the reranker prefilter's accumulator so the
        # Loop's outer edge can carry it to Persistence (which writes it to
        # dropped_reranker.json in the audit folder). The reranker node
        # already accumulates ACROSS iterations on the attrs side; we just
        # need to surface it on the edge here. Empty list when MASF_RERANKER=0.
        "dropped_reranker": list(attrs.get("dropped_reranker") or []),
        "actor_loop_index": int(attrs.get("actor_loop_index") or 0) + 1,
        # Promote latest iteration's surviving signals to the standard key so
        # the Analyst (running outside the loop) can read the run-wide total
        # via surviving_signals_json.
        "surviving_signals_json": json.dumps(all_surviving),
    }


AccumulateActorNode = NodeTemplate(
    CustomNode, forward=_accumulate_actor, pull_keys=None, push_keys=None
)


# ---------- Loop terminate function ----------

def actor_loop_done(_input: dict, attrs: dict) -> bool:
    grouped = attrs.get("documents_by_actor") or []
    return int(attrs.get("actor_loop_index") or 0) >= len(grouped)
