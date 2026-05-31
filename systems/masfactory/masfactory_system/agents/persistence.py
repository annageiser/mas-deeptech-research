"""Persistence — writes signals + audit trail to Supabase and disk.

Pure-Python CustomNode. The Supabase store and per-run audit folder are
injected via graph attributes by `runner.py`.
"""

from __future__ import annotations

import hashlib
import json

from masfactory import CustomNode, NodeTemplate

from ..embedding import compose_signal_text, embed_text, is_enabled as embeddings_enabled
from ..persistence import SignalRow


def _strip_fences_and_tag(raw: str, tag: str | None = None) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    if tag:
        close = f"</{tag}>"
        open_tag = f"<{tag}>"
        if close in text:
            text = text.split(close)[0]
        if open_tag in text:
            text = text.split(open_tag)[1]
    return text.strip()


def _safe_json_load(raw: str, tag: str | None = None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(_strip_fences_and_tag(raw, tag))
    except json.JSONDecodeError:
        return {}


def _persist(_input: dict, attrs: dict) -> dict:
    store = attrs.get("store")
    audit = attrs.get("audit_folder")
    run_id = attrs.get("run_id")

    # Prefer the run-wide accumulators populated by AccumulateActor inside the
    # per-actor Loop. Fall back to the single-pass scratch keys if a caller is
    # running the legacy linear graph (e.g. unit tests or a future config that
    # disables the loop).
    if attrs.get("all_classified") or attrs.get("all_surviving_signals"):
        classified = list(attrs.get("all_classified") or [])
        critique = list(attrs.get("all_critique") or [])
        accumulator_surviving = list(attrs.get("all_surviving_signals") or [])
    else:
        classified = _safe_json_load(attrs.get("classified_json", ""), tag="classified_json").get("classified", [])
        critique = _safe_json_load(attrs.get("critique_json", ""), tag="critique_json").get("decisions", [])
        accumulator_surviving = []

    if accumulator_surviving:
        # AccumulateActor already filtered by Critic decisions per iteration —
        # trust it. (Also avoids re-filtering when critique indices have been
        # rewritten to be run-wide rather than per-iteration.)
        surviving = accumulator_surviving
    else:
        keep_indices = {d["signal_index"] for d in critique if d.get("keep")}
        # Default to keeping everything if the Critic returns no decisions —
        # recall matters more than precision at this stage of the thesis.
        if not critique:
            keep_indices = set(range(len(classified)))
        surviving = [s for i, s in enumerate(classified) if i in keep_indices]

    # ---------- defensive validation: drop hallucinated attributions ----------
    # The LLM has occasionally been observed to attribute a signal to a
    # different actor than the source document's actor (e.g. mentioning PSI
    # inside an SQI page and tagging it as a PSI signal). This breaks the
    # comparative analysis. We enforce: the signal's actor_slug AND source_url
    # must appear together in at least one input document.
    documents = attrs.get("documents") or []
    doc_pairs = {(d.get("actor_slug"), d.get("source_url")) for d in documents}
    doc_actors = {d.get("actor_slug") for d in documents}

    dropped: list[dict] = []
    validated: list[dict] = []
    for s in surviving:
        a, u = s.get("actor_slug"), s.get("source_url")
        # Strict: (actor, url) must match exactly. Fallback if URL drifted:
        # at minimum the actor_slug must be one we fed in this run.
        if (a, u) in doc_pairs or (a in doc_actors and u and any(
            d.get("source_url") == u for d in documents
        )):
            validated.append(s)
        else:
            dropped.append({"signal": s, "reason": "actor_slug/source_url not in input documents"})

    if audit is not None:
        audit.write_json("classifications.json", classified)
        audit.write_json("critique.json", critique)
        audit.write_json("signals.json", validated)
        if dropped:
            audit.write_json("dropped_hallucinations.json", dropped)
        # The per-actor Loop's AccumulateActor records its own
        # cross-actor drops; surface them in the audit too.
        cross_dropped = attrs.get("dropped_cross_actor") or []
        if cross_dropped:
            audit.write_json("dropped_cross_actor.json", cross_dropped)
        brief = attrs.get("brief_md")
        if brief:
            audit.write_text("brief.md", brief if isinstance(brief, str) else str(brief))

    surviving = validated

    inserted = 0
    embed_on = embeddings_enabled()
    embed_count = 0
    if store is not None and run_id is not None and surviving:
        rows: list[SignalRow] = []
        for s in surviving:
            evidence = s.get("evidence_quote") or ""
            content_hash = hashlib.sha256(
                f"{s.get('actor_slug')}|{s.get('source_url')}|{evidence}".encode("utf-8")
            ).hexdigest()
            # Compute embedding if MASF_EMBEDDINGS=1. embed_text returns None
            # if disabled or if model load failed — row insert still works
            # and the column stays NULL.
            emb: list[float] | None = None
            if embed_on:
                emb = embed_text(compose_signal_text(s))
                if emb is not None:
                    embed_count += 1
            rows.append(
                SignalRow(
                    run_id=run_id,
                    actor_slug=s["actor_slug"],
                    source_kind=s["source_kind"],
                    source_url=s["source_url"],
                    title=s.get("title", ""),
                    summary=s.get("summary", ""),
                    evidence_quote=evidence,
                    dimension=s["dimension"],
                    is_technical=bool(s["is_technical"]),
                    confidence=float(s.get("confidence", 0.0)),
                    content_hash=content_hash,
                    embedding=emb,
                )
            )
        inserted = store.insert_signals(rows)
        if audit is not None and embed_on:
            audit.write_json("embeddings_summary.json", {
                "enabled": True,
                "signals_total": len(surviving),
                "signals_embedded": embed_count,
                "model": "BAAI/bge-base-en-v1.5",
                "dim": 768,
            })

    return {
        "signals_kept": len(surviving),
        "signals_inserted": inserted,
        "surviving_signals_json": json.dumps(surviving),
    }


PersistenceNode = NodeTemplate(CustomNode, forward=_persist, pull_keys=None, push_keys=None)
