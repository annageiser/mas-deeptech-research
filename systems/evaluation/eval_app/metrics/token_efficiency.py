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


def token_efficiency(signals_df: pd.DataFrame, tokens_df: pd.DataFrame) -> dict[str, Any]:
    """Per-system signals persisted, tokens consumed, signals per 1k tokens."""
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

        by_system[system] = {
            "label": "System A · MASFactory" if system == "masfactory" else "System B · Hermes",
            "n_signals": n_signals,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "signals_per_1k_tokens": per_1k,
        }

    # Headline comparison numbers for the thesis narrative.
    a = by_system["masfactory"]
    b = by_system["hermes"]
    delta = None
    ratio = None
    if a["signals_per_1k_tokens"] and b["signals_per_1k_tokens"]:
        delta = round(a["signals_per_1k_tokens"] - b["signals_per_1k_tokens"], 4)
        ratio = round(a["signals_per_1k_tokens"] / b["signals_per_1k_tokens"], 3)

    return {
        "metric": "token_efficiency",
        "per_system": by_system,
        "delta_signals_per_1k_tokens": delta,
        "ratio_a_over_b": ratio,
    }
