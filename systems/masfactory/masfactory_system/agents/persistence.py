"""Persistence — writes signals + audit trail to Supabase and disk.

Pure-Python CustomNode. The Supabase store and per-run audit folder are
injected via graph attributes by `runner.py`.

Optional semantic-dedup step (env-gated):
    MASF_SEMANTIC_DEDUP=1 turns it on (requires MASF_EMBEDDINGS=1 — without
    a query embedding, there's nothing to compare against).

    For each candidate signal we query the existing corpus (same actor,
    last MASF_SEMANTIC_DEDUP_DAYS days) for the nearest pgvector neighbour
    and drop the candidate if its cosine similarity exceeds
    MASF_SEMANTIC_DEDUP_THRESHOLD. The dropped signal is logged to the
    audit folder with the matched signal's id so the thesis can report
    dedup rates per actor / per source / per dimension.
"""

from __future__ import annotations

import hashlib
import json
import os

from masfactory import CustomNode, NodeTemplate

from ..classification import normalise_dimension, signal_type_for_dimension
from ..embedding import compose_signal_text, embed_text, is_enabled as embeddings_enabled
from ..persistence import SignalRow
from ..sentiment import score_signal as score_sentiment
from ..structured_output import (
    instructor_repair,
    instructor_repair_available,
    validate_classified_batch,
)


def _semantic_dedup_config() -> tuple[bool, float, int]:
    """(enabled, similarity_threshold, days_back). Defaults: off, 0.92, 90.
    v0.4.0 raised days_back 30 → 90 to expand the scraping window."""
    enabled = os.environ.get("MASF_SEMANTIC_DEDUP", "").strip().lower() in (
        "1", "true", "yes", "on"
    )
    try:
        threshold = float(os.environ.get("MASF_SEMANTIC_DEDUP_THRESHOLD", "0.92"))
    except (TypeError, ValueError):
        threshold = 0.92
    try:
        days_back = int(os.environ.get("MASF_SEMANTIC_DEDUP_DAYS", "90"))
    except (TypeError, ValueError):
        days_back = 90
    # Clamp to sane ranges so a typo doesn't disable / DoS the system.
    threshold = max(0.5, min(0.999, threshold))
    days_back = max(1, min(365, days_back))
    return enabled, threshold, days_back


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

    # User-flagged tuples (Workflow B from docs/wrong-signals-strategy.md):
    # any (actor, url) the user has tagged via the website's flag button
    # is refused re-insertion. Empty set if store unavailable / flags table
    # empty / fetch fails — never raises.
    flagged_tuples: set[tuple[str, str]] = set()
    if store is not None and hasattr(store, "flagged_tuples"):
        try:
            flagged_tuples = store.flagged_tuples()
        except Exception:
            flagged_tuples = set()

    dropped: list[dict] = []
    dropped_flagged: list[dict] = []
    validated: list[dict] = []
    for s in surviving:
        a, u = s.get("actor_slug"), s.get("source_url")
        # First gate: user has previously flagged this exact (actor, url) as
        # wrong → refuse re-insertion forever.
        if (a, u) in flagged_tuples:
            dropped_flagged.append({"signal": s, "reason": "user-flagged tuple"})
            continue
        # Second gate: strict (actor, url) must match exactly. Fallback if
        # URL drifted: at minimum the actor_slug must be one we fed in this run.
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
        if dropped_flagged:
            audit.write_json("dropped_user_flagged.json", dropped_flagged)
        # The per-actor Loop's AccumulateActor records its own
        # cross-actor drops; surface them in the audit too.
        cross_dropped = attrs.get("dropped_cross_actor") or []
        if cross_dropped:
            audit.write_json("dropped_cross_actor.json", cross_dropped)
        # v0.4.23: reranker pre-filter drops, accumulated across actors.
        rerank_dropped = attrs.get("dropped_reranker") or []
        if rerank_dropped:
            audit.write_json("dropped_reranker.json", rerank_dropped)
        brief = attrs.get("brief_md")
        if brief:
            audit.write_text("brief.md", brief if isinstance(brief, str) else str(brief))

    surviving = validated

    # v0.4.22: schema-level validation pass. The Critic + actor-attribution
    # gates only check signal CONTENT; this gate enforces the Classifier's
    # output SHAPE (ClassifiedSignal pydantic model). Invalid rows get
    # dropped to dropped_validation.json so we can see what went wrong.
    # Repair path (MASF_INSTRUCTOR_REPAIR=1) re-prompts OpenRouter to emit
    # a valid version — off by default because it costs tokens.
    schema_valid, schema_invalid = validate_classified_batch(surviving)
    repaired_count = 0
    if instructor_repair_available() and schema_invalid:
        for record in schema_invalid:
            repaired = instructor_repair(record["raw"])
            if repaired is not None:
                schema_valid.append(repaired)
                record["repaired"] = True
                repaired_count += 1
            else:
                record["repaired"] = False
    if audit is not None and schema_invalid:
        audit.write_json("dropped_validation.json", schema_invalid)
    if audit is not None:
        audit.write_json("validation_summary.json", {
            "validated_in": len(surviving),
            "validated_out": len(schema_valid),
            "invalid": len(schema_invalid),
            "repaired": repaired_count,
            "instructor_repair_enabled": instructor_repair_available(),
        })
    surviving = schema_valid

    inserted = 0
    embed_on = embeddings_enabled()
    embed_count = 0
    sem_on, sem_threshold, sem_days = _semantic_dedup_config()
    # Semantic dedup requires embeddings — without a query vector, there's
    # nothing to compare. Soft-disable rather than raise so a stray env
    # combo doesn't break the cron.
    sem_active = sem_on and embed_on and store is not None
    semantic_dedup_log: list[dict] = []

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

            # Semantic dedup: drop if a near-neighbour already exists for
            # this actor. We use a single nearest-neighbour query per
            # signal (~5-15ms via the ivfflat index); for daily batches of
            # ~50 surviving signals that's a sub-second total overhead.
            if sem_active and emb is not None:
                neighbour = store.find_similar_signal(
                    actor_slug=s["actor_slug"],
                    embedding=emb,
                    days_back=sem_days,
                )
                if neighbour and float(neighbour.get("similarity", 0.0)) >= sem_threshold:
                    semantic_dedup_log.append({
                        "dropped_signal": {
                            "actor_slug": s["actor_slug"],
                            "title": s.get("title", "")[:200],
                            "source_url": s.get("source_url"),
                            "dimension": s.get("dimension"),
                        },
                        "matched_existing": {
                            "id": neighbour.get("id"),
                            "title": (neighbour.get("title") or "")[:200],
                            "source_url": neighbour.get("source_url"),
                            "system": neighbour.get("system"),
                            "inserted_at": neighbour.get("inserted_at"),
                        },
                        "similarity": float(neighbour.get("similarity", 0.0)),
                        "threshold": sem_threshold,
                    })
                    continue  # skip the insert

            # Normalise dimension defensively — accepts a v0.3.0 key (and
            # migrates it) or a v0.4.0 key (passes through). Then resolve
            # signal_type from the canonical map, preferring the LLM's
            # value when it provided one and falls back to the dimension-
            # derived value otherwise.
            new_dim = normalise_dimension(s.get("dimension", "") or "")
            sig_type = s.get("signal_type") or signal_type_for_dimension().get(new_dim)

            # v0.4.24 — VADER sentiment (cheap, no LLM call). Both columns
            # remain NULL if disabled / analyzer can't load. Default ON.
            sentiment = score_sentiment(s)
            sentiment_score, sentiment_label = (sentiment if sentiment else (None, None))

            rows.append(
                SignalRow(
                    run_id=run_id,
                    actor_slug=s["actor_slug"],
                    source_kind=s["source_kind"],
                    source_url=s["source_url"],
                    title=s.get("title", ""),
                    summary=s.get("summary", ""),
                    evidence_quote=evidence,
                    dimension=new_dim,
                    is_technical=bool(s["is_technical"]),
                    confidence=float(s.get("confidence", 0.0)),
                    content_hash=content_hash,
                    embedding=emb,
                    signal_type=sig_type,
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label,
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
        if audit is not None and sem_active:
            audit.write_json("semantic_dedup.json", {
                "enabled": True,
                "threshold": sem_threshold,
                "days_back": sem_days,
                "signals_considered": len(surviving),
                "signals_dropped": len(semantic_dedup_log),
                "drops": semantic_dedup_log,
            })

    return {
        "signals_kept": len(surviving),
        "signals_inserted": inserted,
        "surviving_signals_json": json.dumps(surviving),
    }


PersistenceNode = NodeTemplate(CustomNode, forward=_persist, pull_keys=None, push_keys=None)
