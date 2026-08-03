"""Token efficiency — the disposition's "output quality per token cost" metric
in its volume form.

Quality (per-signal accuracy vs gold) is computed separately by
``classification_quality.py``. This module reports the *volume* leg:
**signals persisted per 1k LLM tokens** for each system, plus the raw
token totals and signal counts that go into it.

Why this metric?  Free-tier Nemotron means dollar cost ≈ 0; tokens are
the meaningful unit. Per-1k-token normalisation makes the two systems
directly comparable across runs of unequal size.

Caveat: this is a *volume* metric. A system that produces twice as many
signals per token but at half the precision is not actually more
efficient. The thesis's headline efficiency number (Chapter 3.5) combines
this with the gold-set quality score; this module returns both ingredients.
"""

from __future__ import annotations

from typing import Any

import pandas as pd



# v0.5.7 — a ratio computed from two differently-covered denominators is
# meaningless, and this metric produced exactly that. `public.token_usage` held
# rows for 99% of System A's runs but only 26% of System B's, while the signal
# counts were complete for both. System B therefore got a near-complete
# numerator over a quarter-sized denominator and appeared 8.9x more efficient
# than System A. The like-for-like figure is about 1.4x.
#
# Root cause: only System A writes token_usage. When System B moved from the
# in-house pattern implementation to the upstream Hermes CLI on 2026-06-10, the
# new wrapper (systems/hermes/scripts/persist_signals.py) never recorded tokens,
# so every System B row in that table predates 2026-06-09 and belongs to a
# system that no longer runs. The Hermes CLI does track usage, in its own
# state.db `sessions` table, but nothing copies it into Supabase.
#
# Rather than silently publish a ratio, the metric now measures its own coverage
# and refuses to emit a headline number when the two sides are not comparable.
# See docs/ergebnisse-zusammenfassung.md section 3.1.
MIN_COVERAGE = 0.80
# A ten-point coverage gap already distorts the ratio by around 11 percent,
# which is too much for a number that goes into a thesis as a headline.
MAX_COVERAGE_GAP = 0.10


def token_efficiency(
    signals_df: pd.DataFrame,
    tokens_df: pd.DataFrame,
    runs_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Per-system signals persisted, tokens consumed, signals per 1k tokens.

    `runs_df` is optional but strongly recommended: without it the coverage of
    the token data cannot be established and the ratio cannot be trusted.
    """
    by_system: dict[str, dict[str, Any]] = {}

    for system in ("masfactory", "hermes"):
        # Signals attributable to this system, deduped on the run-grain.
        sigs = signals_df[signals_df["system"] == system] if not signals_df.empty else pd.DataFrame()
        toks = tokens_df[tokens_df["system"] == system] if not tokens_df.empty else pd.DataFrame()

        n_signals = int(len(sigs))
        in_tokens = int(toks["input_tokens"].sum()) if not toks.empty else 0
        out_tokens = int(toks["output_tokens"].sum()) if not toks.empty else 0
        total_tokens = in_tokens + out_tokens

        per_1k = round((n_signals * 1000) / total_tokens, 4) if total_tokens else None

        # How many of this system's successful runs actually contributed tokens?
        coverage = None
        n_runs = n_runs_with_tokens = None
        if runs_df is not None and not runs_df.empty and "system" in runs_df.columns:
            rs = runs_df[runs_df["system"] == system]
            if "status" in rs.columns:
                rs = rs[rs["status"] == "ok"]
            n_runs = int(len(rs))
            run_ids_with_tokens = set(toks["run_id"]) if not toks.empty and "run_id" in toks else set()
            n_runs_with_tokens = int(sum(1 for rid in rs["id"] if rid in run_ids_with_tokens)) \
                if "id" in rs.columns else 0
            coverage = round(n_runs_with_tokens / n_runs, 4) if n_runs else None

        by_system[system] = {
            "label": "System A · MASFactory" if system == "masfactory" else "System B · Hermes",
            "n_signals": n_signals,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "signals_per_1k_tokens": per_1k,
            "n_runs": n_runs,
            "n_runs_with_token_data": n_runs_with_tokens,
            "token_data_coverage": coverage,
        }

    # Headline comparison numbers for the thesis narrative.
    a = by_system["masfactory"]
    b = by_system["hermes"]
    delta = None
    ratio = None
    if a["signals_per_1k_tokens"] and b["signals_per_1k_tokens"]:
        delta = round(a["signals_per_1k_tokens"] - b["signals_per_1k_tokens"], 4)
        ratio = round(a["signals_per_1k_tokens"] / b["signals_per_1k_tokens"], 3)

    # Is the comparison legitimate? Two coverages that differ materially make
    # the ratio an artefact of the bookkeeping rather than of the systems.
    cov_a = a.get("token_data_coverage")
    cov_b = b.get("token_data_coverage")
    warnings: list[str] = []
    comparable = True
    if cov_a is None or cov_b is None:
        comparable = False
        warnings.append(
            "Token-data coverage is unknown because runs_df was not supplied. "
            "The ratio cannot be validated; pass runs_df to enable the check."
        )
    else:
        for name, cov in (("System A", cov_a), ("System B", cov_b)):
            if cov < MIN_COVERAGE:
                comparable = False
                warnings.append(
                    f"{name} has token data for only {cov:.0%} of its successful runs, "
                    f"while its signal count is complete. Its efficiency is overstated "
                    f"by roughly {1/cov:.1f}x."
                )
        if abs(cov_a - cov_b) > MAX_COVERAGE_GAP:
            comparable = False
            warnings.append(
                f"Coverage differs between the systems ({cov_a:.0%} vs {cov_b:.0%}). "
                "A ratio across unequal denominators measures the bookkeeping, not "
                "the systems."
            )
    if warnings:
        warnings.append(
            "Only System A writes public.token_usage. System B's usage lives in the "
            "Hermes CLI's own state.db `sessions` table and is not copied into "
            "Supabase; see docs/ergebnisse-zusammenfassung.md section 3.1 for the "
            "recovery query and the corrected figure."
        )

    return {
        "metric": "token_efficiency",
        "per_system": by_system,
        "delta_signals_per_1k_tokens": delta,
        "ratio_a_over_b": ratio,
        "comparable": comparable,
        "warnings": warnings,
    }
