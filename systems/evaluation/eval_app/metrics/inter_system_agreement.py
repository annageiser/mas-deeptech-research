"""Inter-system agreement — Jaccard overlap between System A and System B.

For each actor with signals from BOTH systems in the window, compute the
Jaccard similarity over the set of ``source_url`` values both systems
emitted (the "are they finding the same things?" question).

Macro = average across actors; weighted = average weighted by the union
size per actor (gives heavier actors more weight). Both are reported.

Why this metric?  The disposition's SRQ4 (gap analysis) asks how
different the two architectures' outputs are on the same task. Per-actor
URL-set Jaccard is the most direct possible answer: it says nothing about
quality, only about coverage overlap. Quality is the gold-set metric
(classification_quality.py).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def inter_system_agreement(signals_df: pd.DataFrame) -> dict[str, Any]:
    """Return per-actor Jaccard + macro/weighted aggregates + counts."""
    if signals_df.empty:
        return _empty()

    # Drop rows without the two columns we need.
    df = signals_df[["actor_slug", "system", "source_url"]].dropna()
    if df.empty:
        return _empty()

    # URL sets per (actor, system).
    by = df.groupby(["actor_slug", "system"])["source_url"].apply(set)

    # Compute actor_buckets up-front so the "only_a"/"only_b" counts are
    # reported even when no actor has signals from both systems (which is
    # the expected state very early in the cron's life).
    actor_buckets = {"both": 0, "only_a": 0, "only_b": 0}
    per_actor: list[dict] = []
    for actor in by.index.get_level_values(0).unique():
        a = by.get((actor, "masfactory"), set())
        b = by.get((actor, "hermes"), set())
        if a and b:
            actor_buckets["both"] += 1
            union = a | b
            inter = a & b
            jacc = len(inter) / len(union) if union else 0.0
            per_actor.append({
                "actor_slug": actor,
                "n_a": len(a),
                "n_b": len(b),
                "n_intersection": len(inter),
                "n_union": len(union),
                "jaccard": round(jacc, 4),
            })
        elif a and not b:
            actor_buckets["only_a"] += 1
        elif b and not a:
            actor_buckets["only_b"] += 1

    if not per_actor:
        # No actor was seen by BOTH systems — agreement is undefined, but the
        # bucket counts are still meaningful (operators want to know that the
        # systems are reaching disjoint actor pools).
        return {
            "metric": "inter_system_agreement",
            "n_actors_compared": 0,
            "actor_buckets": actor_buckets,
            "jaccard_macro": None,
            "jaccard_weighted": None,
            "per_actor": [],
        }

    # Aggregates over actors-seen-by-both.
    per_actor.sort(key=lambda r: -r["jaccard"])
    weights = [r["n_union"] for r in per_actor]
    total_weight = sum(weights)
    jacc_macro = round(sum(r["jaccard"] for r in per_actor) / len(per_actor), 4)
    jacc_weighted = round(
        sum(r["jaccard"] * r["n_union"] for r in per_actor) / total_weight, 4
    ) if total_weight else 0.0

    return {
        "metric": "inter_system_agreement",
        "n_actors_compared": len(per_actor),
        "actor_buckets": actor_buckets,
        "jaccard_macro": jacc_macro,
        "jaccard_weighted": jacc_weighted,
        "per_actor": per_actor,
    }


def _empty() -> dict[str, Any]:
    return {
        "metric": "inter_system_agreement",
        "n_actors_compared": 0,
        "actor_buckets": {"both": 0, "only_a": 0, "only_b": 0},
        "jaccard_macro": None,
        "jaccard_weighted": None,
        "per_actor": [],
    }
