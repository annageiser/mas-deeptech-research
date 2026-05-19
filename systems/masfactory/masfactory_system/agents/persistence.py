"""Persistence — writes signals + audit trail to Supabase and disk.

Pure-Python CustomNode. The Supabase store and per-run audit folder are
injected via graph attributes by `runner.py`.
"""

from __future__ import annotations

import hashlib
import json

from masfactory import CustomNode, NodeTemplate

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

    classified = _safe_json_load(attrs.get("classified_json", ""), tag="classified_json").get("classified", [])
    critique = _safe_json_load(attrs.get("critique_json", ""), tag="critique_json").get("decisions", [])

    keep_indices = {d["signal_index"] for d in critique if d.get("keep")}
    # Default to keeping everything if the Critic returns no decisions — recall
    # matters more than precision at this stage of the thesis.
    if not critique:
        keep_indices = set(range(len(classified)))
    surviving = [s for i, s in enumerate(classified) if i in keep_indices]

    if audit is not None:
        audit.write_json("classifications.json", classified)
        audit.write_json("critique.json", critique)
        audit.write_json("signals.json", surviving)
        brief = attrs.get("brief_md")
        if brief:
            audit.write_text("brief.md", brief if isinstance(brief, str) else str(brief))

    inserted = 0
    if store is not None and run_id is not None and surviving:
        rows: list[SignalRow] = []
        for s in surviving:
            evidence = s.get("evidence_quote") or ""
            content_hash = hashlib.sha256(
                f"{s.get('actor_slug')}|{s.get('source_url')}|{evidence}".encode("utf-8")
            ).hexdigest()
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
                )
            )
        inserted = store.insert_signals(rows)

    return {
        "signals_kept": len(surviving),
        "signals_inserted": inserted,
        "surviving_signals_json": json.dumps(surviving),
    }


PersistenceNode = NodeTemplate(CustomNode, forward=_persist, pull_keys=None, push_keys=None)
