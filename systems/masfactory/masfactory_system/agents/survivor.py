"""Survivor — pure-Python filter between Critic and Analyst.

The Analyst needs the **surviving** classified signals to write its brief.
Before this node existed, the graph wired ("critic", "analyst",
{"surviving_signals_json": ...}) — but Critic only emits `critique_json`,
not `surviving_signals_json`. The Analyst then received the default empty
string and hallucinated a brief from plan_json alone (training-data leak
on prominent actors). This node closes that loop deterministically.

Reads:  `classified_json`, `critique_json`
Writes: `surviving_signals_json` (the JSON-encoded list of classified
        signals the Critic kept)
"""

from __future__ import annotations

import json

from masfactory import CustomNode, NodeTemplate


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


def _survive(_input: dict, attrs: dict) -> dict:
    classified = _safe_json_load(attrs.get("classified_json", ""), tag="classified_json").get("classified", [])
    critique = _safe_json_load(attrs.get("critique_json", ""), tag="critique_json").get("decisions", [])

    keep_indices = {d["signal_index"] for d in critique if d.get("keep")}
    # If the Critic returned no decisions, default to keeping everything.
    # Better to over-show the Analyst than to silently lose signals.
    if not critique:
        keep_indices = set(range(len(classified)))

    surviving = [s for i, s in enumerate(classified) if i in keep_indices]
    return {
        "surviving_signals_json": json.dumps(surviving),
        "signals_kept": len(surviving),
    }


SurvivorNode = NodeTemplate(CustomNode, forward=_survive, pull_keys=None, push_keys=None)
