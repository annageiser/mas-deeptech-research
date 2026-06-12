"""v0.4.23 — bge-reranker cross-encoder pre-filter ahead of the Critic.

Sits between the Classifier and the Critic in the per-actor Loop. Reads
`classified_json`, scores each signal against an actor-specific
relevance query with a cross-encoder, optionally drops below-threshold
candidates, and writes back to `classified_json` (so the downstream
Critic sees a smaller, more-relevant batch).

Default behaviour when the reranker is **off** (no MASF_RERANKER=1): the
node is a pure pass-through — it doesn't touch the JSON. Off is the
default so existing pipelines aren't perturbed.

When **on**: each signal gains a `reranker_score` field for downstream
analytics. Signals with score < MASF_RERANKER_THRESHOLD get dropped.
Drops are surfaced via a per-iteration `dropped_reranker` accumulator on
attrs, which AccumulateActor / Persistence can later audit.

Design choices:
  - Pure CustomNode (no LLM call) — sub-100ms warm per actor for
    typical batches of <=20 signals.
  - Per-actor query construction (compose_actor_query) means the
    Critic sees signals that are *about this actor's quantum work*,
    not generic mentions.
  - Scoring is best-effort: if the model fails to load (offline, ONNX
    issue), we log and pass through. Recall > precision at the
    pre-filter stage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from masfactory import CustomNode, NodeTemplate

from .. import reranker
from ..reranker import compose_actor_query, compose_signal_doc

log = logging.getLogger(__name__)


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


def _rerank_prefilter(_input: dict, attrs: dict) -> dict:
    """Score + filter the current actor's classified candidates.

    Outputs a single key `classified_json` so the downstream Critic
    consumes a (possibly smaller) list. Adds `reranker_score` to each
    surviving entry. The pass-through path returns the input untouched.
    """
    raw_classified_json = attrs.get("classified_json", "") or ""

    # Off → pure passthrough so the graph layout is stable.
    if not reranker.is_enabled():
        return {"classified_json": raw_classified_json}

    parsed = _safe_json_load(raw_classified_json, tag="classified_json")
    classified: list[dict] = parsed.get("classified", []) if isinstance(parsed, dict) else []
    if not classified:
        return {"classified_json": raw_classified_json}

    # Look up the current actor in the pool. If we can't, pass through.
    current_slug = attrs.get("current_actor_slug") or ""
    actor_pool = attrs.get("actor_pool") or []
    actor: dict[str, Any] = {}
    for a in actor_pool:
        if a.get("slug") == current_slug:
            actor = a
            break
    if not actor and current_slug:
        actor = {"slug": current_slug, "name": current_slug, "category": ""}

    query = compose_actor_query(actor)
    docs = [compose_signal_doc(s) for s in classified]
    scores = reranker.score_pairs(query, docs)

    if scores is None or len(scores) != len(classified):
        # Failed scoring → leave the batch untouched. Don't crash the cron.
        return {"classified_json": raw_classified_json}

    threshold = reranker.threshold()
    kept: list[dict] = []
    dropped: list[dict] = []
    for signal, score in zip(classified, scores):
        annotated = dict(signal)
        annotated["reranker_score"] = round(float(score), 4)
        if score < threshold:
            dropped.append({
                "actor_slug": signal.get("actor_slug"),
                "title": (signal.get("title") or "")[:200],
                "reranker_score": annotated["reranker_score"],
                "threshold": threshold,
            })
        else:
            kept.append(annotated)

    # Audit accumulator — Persistence can surface it per-run if it wants.
    existing = attrs.get("dropped_reranker") or []
    new_accumulator = list(existing) + dropped

    return {
        "classified_json": json.dumps({"classified": kept}),
        "dropped_reranker": new_accumulator,
    }


RerankerPreFilterNode = NodeTemplate(
    CustomNode, forward=_rerank_prefilter, pull_keys=None, push_keys=None
)
