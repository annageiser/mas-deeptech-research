"""Write the harness output: a results.json + a thesis-ready results.md.

The markdown summary is what Chapter 3.5 (Empirical Results) cites
directly. Numbers are not rounded further — the harness controls
rounding so the docs and the JSON cannot drift.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def write_results(results: dict[str, Any], *, output_dir: str) -> dict[str, str]:
    """Materialise results.json + results.md in a timestamped subfolder.

    Returns paths for the caller's run log."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    folder = os.path.join(output_dir, stamp)
    os.makedirs(folder, exist_ok=True)

    json_path = os.path.join(folder, "results.json")
    md_path = os.path.join(folder, "results.md")

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_render_markdown(results, stamp))

    return {"json_path": json_path, "md_path": md_path, "folder": folder}


def _render_markdown(results: dict[str, Any], stamp: str) -> str:
    lines: list[str] = []
    lines.append(f"# Evaluation results — {stamp} UTC")
    lines.append("")
    lines.append("Computed by `python -m eval_app.runner all` from the live Supabase. "
                 "Settings + window are recorded in `results.json` for full reproducibility.")
    lines.append("")

    # ---- Inter-system agreement ----
    isa = results.get("inter_system_agreement") or {}
    lines.append("## Inter-system agreement (Jaccard over signal source_url, per actor)")
    if isa.get("n_actors_compared", 0) == 0:
        lines.append("")
        lines.append("**No actors yet have signals from both systems in the window.**")
        lines.append("This is expected very early in the cron's life; expect this to populate within the first week of dual-system runs.")
    else:
        lines.append("")
        buckets = isa.get("actor_buckets", {})
        lines.append(f"- Actors with signals from **both** systems: **{buckets.get('both', 0)}**")
        lines.append(f"- Actors with signals from **only System A**: {buckets.get('only_a', 0)}")
        lines.append(f"- Actors with signals from **only System B**: {buckets.get('only_b', 0)}")
        lines.append(f"- **Macro Jaccard** (mean across actors): **{isa.get('jaccard_macro')}**")
        lines.append(f"- **Weighted Jaccard** (weighted by union size): **{isa.get('jaccard_weighted')}**")
        lines.append("")
        lines.append("Interpretation: a Jaccard of 1.0 means perfect overlap; 0.0 means disjoint signal sets. ")
        lines.append("The thesis reports this as the answer to 'how much do the two architectures find the same things on the same task?'")
    lines.append("")

    # ---- Token efficiency ----
    te = results.get("token_efficiency") or {}
    lines.append("## Token efficiency (signals persisted per 1 000 LLM tokens)")
    lines.append("")
    per = te.get("per_system", {})
    lines.append("| System | Signals | Input tokens | Output tokens | Total | **Signals / 1k tokens** |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for k in ("masfactory", "hermes"):
        row = per.get(k, {})
        lines.append(
            f"| {row.get('label', k)} | {row.get('n_signals', 0)} | {row.get('input_tokens', 0):,} | "
            f"{row.get('output_tokens', 0):,} | {row.get('total_tokens', 0):,} | "
            f"**{row.get('signals_per_1k_tokens') if row.get('signals_per_1k_tokens') is not None else '—'}** |"
        )
    delta = te.get("delta_signals_per_1k_tokens")
    ratio = te.get("ratio_a_over_b")
    if delta is not None:
        lines.append("")
        lines.append(f"- **System A − System B** (signals / 1k tokens): {delta:+.4f}")
        lines.append(f"- **Ratio A / B**: {ratio:.3f}× (>1 means System A is more token-efficient)")
        lines.append("")
        lines.append("Caveat: this is the *volume* leg of the disposition's 'output quality per token cost' metric. ")
        lines.append("The thesis's headline efficiency number combines this with the gold-set classification quality below.")
    lines.append("")

    # ---- Classification quality (vs gold) ----
    cq = results.get("classification_quality") or {}
    lines.append("## Classification quality (vs hand-labelled gold set)")
    lines.append("")
    status = cq.get("status")
    if status == "no_gold_set":
        lines.append(f"**Gold set pending.** {cq.get('note')}")
    elif status == "empty_gold_set":
        lines.append(f"Gold set file present but empty: `{cq.get('gold_path')}`")
    elif status == "no_overlap":
        lines.append(f"**Gold set has {cq.get('n_gold')} labels but none overlap the current evaluation window.** {cq.get('note', '')}")
    elif status == "no_signals_in_window":
        lines.append(f"Gold set has {cq.get('n_gold')} labels but no signals are in the current window. Widen `EVAL_WINDOW_DAYS`.")
    elif status == "ok":
        lines.append(f"Gold labels: **{cq.get('n_gold')}** total · **{cq.get('n_matched')}** in current window.")
        lines.append("")
        eco = cq.get("ecosystem_overall", {})
        for axis_name, axis_label in (
            ("signal_type", "Ehrenthal signal type (4-way classification)"),
            ("dimension", "Dimension (19-way classification)"),
            ("keep_decision", "Keep decision (Critic vs gold)"),
        ):
            blk = eco.get(axis_name, {})
            if not blk.get("available"):
                continue
            lines.append(f"### {axis_label}")
            lines.append(f"- n = {blk['n']}")
            lines.append(f"- accuracy = **{blk['accuracy']}**, macro F1 = **{blk['f1_macro']}**, Cohen κ = **{blk['cohen_kappa']}**")
            lines.append(f"- macro precision / recall = {blk['precision_macro']} / {blk['recall_macro']}")
            lines.append("")
    else:
        lines.append(f"Unknown status: `{status}`")
    lines.append("")

    # ---- Reproducibility ----
    rp = results.get("reproducibility") or {}
    lines.append("## Reproducibility (re-run Jaccard over each run's FOUND set)")
    lines.append("")
    if rp.get("status") == "no_artefacts":
        lines.append("**Run artefacts not reachable.** " + str(rp.get("note", "")))
        lines.append("")
        lines.append(
            "This metric deliberately does NOT use `public.signals`. Signals attach to "
            "the run that first inserted them, and the unique key means a re-run that "
            "rediscovers the same URL inserts nothing — so consecutive runs' inserted "
            "sets are near-disjoint by construction and any Jaccard computed over them "
            "is an artefact of the deduplicating store rather than a property of the "
            "system."
        )
        per_rp = {}
        n_total = 0
    else:
        per_rp = rp.get("per_system", {})
        n_total = sum(p.get("n_comparisons", 0) for p in per_rp.values())
    if rp.get("status") == "no_artefacts":
        pass
    elif n_total == 0:
        lines.append("**No re-run pairs yet** (need ≥ 2 runs of the same system that each found something, over an overlapping actor cohort).")
    else:
        lines.append("| System | # comparisons | Jaccard mean | min | max |")
        lines.append("|---|---:|---:|---:|---:|")
        for k in ("masfactory", "hermes"):
            row = per_rp.get(k, {})
            lines.append(
                f"| {k} | {row.get('n_comparisons', 0)} | "
                f"{row.get('jaccard_mean') if row.get('jaccard_mean') is not None else '—'} | "
                f"{row.get('jaccard_min') if row.get('jaccard_min') is not None else '—'} | "
                f"{row.get('jaccard_max') if row.get('jaccard_max') is not None else '—'} |"
            )
        lines.append("")
        lines.append("Interpretation: a re-run Jaccard < 1.0 reflects (a) model non-determinism at temperature > 0 and (b) underlying source-list freshness (Google News / Bing News rotate hourly). The metric calibrates the credibility-mechanism story — even a system fed exclusively costly signals doesn't reproduce 100% because the *world* isn't reproducible.")
        lines.append("")
        lines.append(
            "Basis: " + str(rp.get("basis", "")) + ". Computed from the run artefacts "
            "(System A's audit folders, System B's per-actor agent output), NOT from "
            "`public.signals`. Signals attach to the run that first inserted them, so a "
            "re-run that rediscovers the same URL contributes no rows and a Jaccard "
            "computed over inserted sets measures the deduplicating store rather than "
            "the system. That figure is retained in results.json under "
            "`reproducibility_inserted_sets` as a diagnostic only."
        )
    lines.append("")

    # ---- Settings ----
    settings = results.get("settings") or {}
    lines.append("## Settings recorded for this run")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(settings, indent=2))
    lines.append("```")

    return "\n".join(lines) + "\n"
