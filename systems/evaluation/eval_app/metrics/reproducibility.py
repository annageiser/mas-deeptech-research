"""Reproducibility — re-run delta on a fixed actor cohort.

The constructive-research methodology (Kasanen et al. 1993) commits to
reproducibility. This metric quantifies it: for each pair of completed
runs of the same system with the *same actor cohort* and the *same
config snapshot*, what fraction of signals re-emerge?

Operational definition:
  - Group runs by (system, sorted-actor-slugs, config_hash).
  - For each group with ≥ 2 successful runs, take the latest two.
  - Compute Jaccard on the (actor_slug, source_url, content_hash)
    tuples of the persisted signals.
  - Aggregate across groups: per-system mean + count of comparisons.

Why a re-run gap is expected:
  - Model non-determinism (temperature > 0 in chat completions)
  - Source freshness — Google News / Bing News results turn over hourly
  - Search-query equivalence — same query may rank differently across calls

The thesis reports this number, not as "the system is broken" but as a
calibration of the credibility-mechanism story: even a system fed
exclusively costly signals doesn't reproduce 100% because the *world*
isn't reproducible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


def _config_hash(config: Any) -> str:
    """Stable hash of a config dict (or None)."""
    try:
        s = json.dumps(config, sort_keys=True, default=str)
    except Exception:
        s = str(config)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def reproducibility(runs_df: pd.DataFrame, signals_df: pd.DataFrame) -> dict[str, Any]:
    """Per-system re-run Jaccard + per-comparison detail."""
    if runs_df.empty or signals_df.empty:
        return _empty()

    # Only `ok` runs participate. An errored run isn't a fair comparator.
    ok_runs = runs_df[runs_df["status"] == "ok"].copy() if "status" in runs_df.columns else runs_df.copy()
    if ok_runs.empty:
        return _empty()

    # Group key.
    def _key(row):
        slugs = sorted(row.get("actor_slugs") or [])
        return (row["system"], "|".join(slugs))

    ok_runs["__key"] = ok_runs.apply(_key, axis=1)

    per_comparison: list[dict] = []

    for key, group in ok_runs.groupby("__key"):
        if len(group) < 2:
            continue
        # Take the two most recent runs from this group.
        group = group.sort_values("started_at", ascending=False).head(2)
        ids = group["id"].tolist()
        sig_a = signals_df[signals_df["run_id"] == ids[0]]
        sig_b = signals_df[signals_df["run_id"] == ids[1]]
        if sig_a.empty or sig_b.empty:
            continue

        def _tuples(df):
            return {
                (row["actor_slug"], row["source_url"])
                for _, row in df[["actor_slug", "source_url"]].dropna().iterrows()
            }

        ta = _tuples(sig_a)
        tb = _tuples(sig_b)
        if not ta or not tb:
            continue
        union = ta | tb
        inter = ta & tb
        jacc = round(len(inter) / len(union), 4) if union else 0.0
        per_comparison.append({
            "system": key[0],
            "run_a": ids[0],
            "run_b": ids[1],
            "n_signals_a": len(ta),
            "n_signals_b": len(tb),
            "n_intersection": len(inter),
            "n_union": len(union),
            "jaccard": jacc,
        })

    by_system: dict[str, dict[str, Any]] = {}
    for sys_key in ("masfactory", "hermes"):
        my = [c for c in per_comparison if c["system"] == sys_key]
        if not my:
            by_system[sys_key] = {"n_comparisons": 0, "jaccard_mean": None, "jaccard_min": None}
        else:
            by_system[sys_key] = {
                "n_comparisons": len(my),
                "jaccard_mean": round(sum(c["jaccard"] for c in my) / len(my), 4),
                "jaccard_min": round(min(c["jaccard"] for c in my), 4),
                "jaccard_max": round(max(c["jaccard"] for c in my), 4),
            }

    return {
        "metric": "reproducibility",
        "per_system": by_system,
        "per_comparison": per_comparison,
    }


def _empty() -> dict[str, Any]:
    return {
        "metric": "reproducibility",
        "per_system": {
            "masfactory": {"n_comparisons": 0, "jaccard_mean": None, "jaccard_min": None},
            "hermes": {"n_comparisons": 0, "jaccard_mean": None, "jaccard_min": None},
        },
        "per_comparison": [],
    }


# ---------------------------------------------------------------------------
# v0.5.6 — reproducibility over FOUND sets rather than inserted sets.
#
# `reproducibility()` above compares the signals attached to each run_id in
# public.signals. Signals attach to the run that FIRST inserted them, and the
# unique key means a re-run that rediscovers the same URL inserts nothing, so
# its run_id carries no rows. Consecutive runs' inserted sets are therefore
# near-disjoint BY CONSTRUCTION and the resulting Jaccard is an artefact of the
# deduplicating store, not a property of the system.
#
# Measured on production: System A's two most recent runs both attached zero
# signals, which is why the metric reported zero comparisons for it, and System
# B's 0.155 is depressed by the same mechanism.
#
# This version reads what each run actually FOUND from the run artefacts (see
# eval_app/found_sets.py) and compares consecutive runs of the same system,
# restricted to the actors BOTH runs attempted so cohort differences cannot
# masquerade as non-determinism.
# ---------------------------------------------------------------------------

def reproducibility_from_found_sets(runs, *, max_pairs_per_system: int = 12) -> dict:
    """Per-system re-run Jaccard over found sets.

    `runs` is an iterable of eval_app.found_sets.RunFoundSet.
    """
    by_system: dict[str, list] = {}
    for r in runs:
        by_system.setdefault(r.system, []).append(r)

    per_comparison: list[dict] = []
    per_system: dict[str, dict] = {}

    for system, group in by_system.items():
        # Oldest to newest; runs without a parseable timestamp sort last.
        group = sorted(group, key=lambda r: (r.started_at is None, r.started_at or 0))
        # Only runs that found something can evidence reproducibility. A pair of
        # empty runs is trivially "identical" and would inflate the mean.
        usable = [r for r in group if r.pairs]
        jaccards: list[float] = []

        for a, b in list(zip(usable, usable[1:]))[-max_pairs_per_system:]:
            shared_actors = a.actors & b.actors
            if not shared_actors:
                continue
            pa = {p for p in a.pairs if p[0] in shared_actors}
            pb = {p for p in b.pairs if p[0] in shared_actors}
            union = pa | pb
            if not union:
                continue
            jacc = len(pa & pb) / len(union)
            jaccards.append(jacc)
            per_comparison.append({
                "system": system,
                "run_a": a.run_key,
                "run_b": b.run_key,
                "n_shared_actors": len(shared_actors),
                "n_a": len(pa),
                "n_b": len(pb),
                "n_intersection": len(pa & pb),
                "n_union": len(union),
                "jaccard": round(jacc, 4),
            })

        per_system[system] = {
            "n_comparisons": len(jaccards),
            "jaccard_mean": round(sum(jaccards) / len(jaccards), 4) if jaccards else None,
            "jaccard_min": round(min(jaccards), 4) if jaccards else None,
            "jaccard_max": round(max(jaccards), 4) if jaccards else None,
            "n_runs_seen": len(group),
            "n_runs_with_findings": len(usable),
        }

    return {
        "metric": "reproducibility_from_found_sets",
        "basis": (
            "consecutive runs of the same system, compared on the (actor, "
            "source_url) pairs each run FOUND, restricted to actors both runs "
            "attempted"
        ),
        "per_system": per_system,
        "per_comparison": per_comparison,
    }
