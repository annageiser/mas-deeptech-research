"""Signal classification schema (loaded from schema.yaml)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Return the parsed signal-classification schema."""
    with resources.files(__package__).joinpath("schema.yaml").open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def schema_as_prompt_block() -> str:
    """Render the schema as a compact prompt block for agent instructions.

    Groups dimensions by Ehrenthal's signal_type so the LLM can reason at
    the four-signal level first, then pick the matching sub-category.
    """
    schema = load_schema()
    by_type: dict[str, list[dict[str, Any]]] = {}
    for dim in schema["dimensions"]:
        by_type.setdefault(dim["signal_type"], []).append(dim)

    type_meta = {st["key"]: st for st in schema.get("signal_types", [])}
    lines = [
        "Signal classification taxonomy (Ehrenthal et al. 2026 four-signal scheme).",
        "First pick the signal_type, then the dimension within it. Output BOTH.",
        "",
    ]
    for st_key in ("legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory"):
        st = type_meta.get(st_key, {})
        lines.append(f"== signal_type: {st_key} ({st.get('short_label', st_key)}) ==")
        for dim in by_type.get(st_key, []):
            tech = "technical" if dim["is_technical"] else "non-technical"
            lines.append(f"  - {dim['key']} ({tech}, cost={dim['signal_cost']}): {dim['description'].strip()}")
        lines.append("")
    lines.append("Each signal MUST quote a short verbatim snippet from the source as `evidence_quote`.")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def signal_type_for_dimension() -> dict[str, str]:
    """dimension key -> signal_type key (one of Ehrenthal's four)."""
    return {d["key"]: d["signal_type"] for d in load_schema()["dimensions"]}


@lru_cache(maxsize=1)
def legacy_dimension_map() -> dict[str, str]:
    """v0.3.0 dimension key -> v0.4.0 dimension key (the canonical migration table).

    Used by the SQL migration in schema.sql AND by code paths that may still
    encounter legacy values (e.g. an old run replayed locally before the
    migration was applied). Source of truth is the `legacy_dimensions:` field
    on each v0.4.0 entry — we invert it here so the lookup is one-step."""
    out: dict[str, str] = {}
    for dim in load_schema()["dimensions"]:
        for legacy_key in dim.get("legacy_dimensions") or []:
            out[legacy_key] = dim["key"]
    return out


def normalise_dimension(key: str) -> str:
    """Best-effort lookup: v0.4.0 key passes through; v0.3.0 key gets remapped."""
    if not key:
        return key
    schema = load_schema()
    valid = {d["key"] for d in schema["dimensions"]}
    if key in valid:
        return key
    return legacy_dimension_map().get(key, key)


def few_shot_examples_block(examples: list[dict]) -> str:
    """v0.4.2 — render Anna's hand-labelled gold examples as a few-shot
    block for the Classifier prompt. Empty list → empty string (prompt
    runs without few-shot, same as v0.4.1).

    Each example: actor_slug, dimension, signal_type, evidence_quote,
    title, anna_note. Format compact so it survives a tight context budget.
    """
    if not examples:
        return ""
    lines: list[str] = [
        "",
        "## Hand-labelled gold examples (from the researcher's parallel coding)",
        "These are EXEMPLAR signals that the researcher (Anna Geiser) has",
        "manually verified as correct classifications. Use them as anchors",
        "for similar evidence quotes; do not pattern-match too narrowly.",
        "",
    ]
    for i, ex in enumerate(examples, 1):
        dim = ex.get("dimension", "?")
        st = ex.get("signal_type") or "?"
        actor = ex.get("actor_slug", "?")
        quote = (ex.get("evidence_quote") or "").strip().replace("\n", " ")[:240]
        note = (ex.get("anna_note") or "").strip().replace("\n", " ")[:160]
        lines.append(f"{i}. actor={actor}  signal_type={st}  dimension={dim}")
        lines.append(f"   evidence: \"{quote}\"")
        if note:
            lines.append(f"   researcher note: {note}")
    lines.append("")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def dimension_cost_map() -> dict[str, str]:
    """dimension key -> signal_cost class ('high'|'medium'|'low')."""
    return {d["key"]: d.get("signal_cost", "medium") for d in load_schema()["dimensions"]}


@lru_cache(maxsize=1)
def dimension_observability_map() -> dict[str, str]:
    """dimension key -> observability class ('high'|'medium'|'low')."""
    return {d["key"]: d.get("observability", "medium") for d in load_schema()["dimensions"]}


@lru_cache(maxsize=1)
def cost_multipliers() -> dict[str, float]:
    """cost class -> credibility multiplier (from schema `cost_classes`)."""
    classes = load_schema().get("cost_classes", {})
    return {k: float(v.get("multiplier", 0.7)) for k, v in classes.items()}
