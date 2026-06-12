"""B.3 — Coverage metric: signals/actor/week per source_kind.

Two thesis-relevant questions this answers:
  1. Are we collecting evenly across the 40 seeded actors?
     (Or is the corpus dominated by a long-tail of one or two prolific actors?)
  2. Is the source mix balanced across arXiv / website / news / patent?
     (A system that only ever produces 'website' signals fails Ehrenthal's
     four-source plurality requirement.)

Read-only aggregation over the same `public.signals` view used elsewhere —
no schema additions.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from . import data_access as da
from . import labels as L


def coverage_payload(system: Optional[str], days: int) -> dict[str, Any]:
    sig = da.signals(system=system, days=days)
    actors_df = da.actors()

    actor_name = (
        dict(zip(actors_df["slug"], actors_df["name"]))
        if not actors_df.empty else {}
    )
    actor_cat = (
        dict(zip(actors_df["slug"], actors_df["category"]))
        if not actors_df.empty else {}
    )
    actors_total = int(len(actors_df))

    if sig.empty:
        return {
            "summary": {
                "total_signals": 0,
                "actors_with_signals": 0,
                "actors_total": actors_total,
                "coverage_pct": 0.0,
                "weeks": 0,
                "source_kinds": 0,
            },
            "per_source_kind": [],
            "per_actor": _zero_rows(actor_name, actor_cat),
            "weekly": [],
        }

    sig = sig.copy()
    sig["inserted_at_dt"] = pd.to_datetime(sig["inserted_at"], errors="coerce", utc=True)
    iso = sig["inserted_at_dt"].dt.isocalendar()
    sig["iso_week"] = (
        iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    )

    # ---- per source_kind (ecosystem-wide mix) ----
    sk = sig.groupby("source_kind").size().reset_index(name="count")
    total = int(sk["count"].sum()) or 1
    per_source_kind = [
        {
            "source_kind": r["source_kind"],
            "label": L.source_kind(r["source_kind"]),
            "count": int(r["count"]),
            "pct": round(100 * r["count"] / total, 1),
        }
        for _, r in sk.sort_values("count", ascending=False).iterrows()
    ]

    # ---- per actor (with the per-source-kind grid) ----
    grid = sig.groupby(["actor_slug", "source_kind"]).size().unstack(fill_value=0)
    per_actor: list[dict[str, Any]] = []
    for slug, row in grid.iterrows():
        by_src = {k: int(v) for k, v in row.items() if v > 0}
        weeks_active = int(
            sig.loc[sig["actor_slug"] == slug, "iso_week"].nunique()
        )
        cat = actor_cat.get(slug)
        per_actor.append({
            "actor_slug": slug,
            "name": actor_name.get(slug, slug),
            "category": cat,
            "category_label": L.category(cat) if cat else None,
            "total": int(row.sum()),
            "weeks_active": weeks_active,
            "source_kinds": len(by_src),
            "by_source_kind": by_src,
        })

    # Actors seeded in `actors` but with zero signals in the window — these
    # are the gaps the metric exists to surface.
    seen = {a["actor_slug"] for a in per_actor}
    for slug, name in actor_name.items():
        if slug in seen:
            continue
        cat = actor_cat.get(slug)
        per_actor.append({
            "actor_slug": slug,
            "name": name,
            "category": cat,
            "category_label": L.category(cat) if cat else None,
            "total": 0,
            "weeks_active": 0,
            "source_kinds": 0,
            "by_source_kind": {},
        })
    per_actor.sort(key=lambda a: (-a["total"], a["name"].lower()))

    # ---- weekly trend ----
    weekly: list[dict[str, Any]] = []
    for week, wk_df in sig.groupby("iso_week"):
        weekly.append({
            "iso_week": str(week),
            "total": int(len(wk_df)),
            "by_source_kind": {
                str(k): int(v) for k, v in wk_df["source_kind"].value_counts().items()
            },
        })
    weekly.sort(key=lambda w: w["iso_week"])

    actors_with_signals = sum(1 for a in per_actor if a["total"] > 0)
    return {
        "summary": {
            "total_signals": int(len(sig)),
            "actors_with_signals": actors_with_signals,
            "actors_total": actors_total,
            "coverage_pct": (
                round(100 * actors_with_signals / actors_total, 1)
                if actors_total else 0.0
            ),
            "weeks": int(sig["iso_week"].nunique()),
            "source_kinds": int(sig["source_kind"].nunique()),
        },
        "per_source_kind": per_source_kind,
        "per_actor": per_actor,
        "weekly": weekly,
    }


def _zero_rows(actor_name: dict, actor_cat: dict) -> list[dict[str, Any]]:
    rows = []
    for slug, name in actor_name.items():
        cat = actor_cat.get(slug)
        rows.append({
            "actor_slug": slug,
            "name": name,
            "category": cat,
            "category_label": L.category(cat) if cat else None,
            "total": 0,
            "weeks_active": 0,
            "source_kinds": 0,
            "by_source_kind": {},
        })
    rows.sort(key=lambda a: a["name"].lower())
    return rows
