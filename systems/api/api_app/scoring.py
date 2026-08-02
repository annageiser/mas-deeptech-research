"""Actor scoring — Impact, Credibility, Momentum, Diversity, Authority,
cheap-talk ratio. Originally vendored from the Streamlit dashboard's
scoring module; that package was retired on 2026-08-02 and this is now the
single implementation.

References (cited on the Methodology endpoint):
- Ehrenthal, Gonzalez-Padron & Gruen (2026) — noncommensurable performance
- Suchman (1995) — legitimacy as receiver-side signal evaluation
- Rieger, Dreller & Engelen (2025) — costly signals predict VC funding
- Knight & Cavusgil (2004) — capability-based competitive advantage
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .labels import (
    CAPABILITY_DIMENSIONS,
    COST_MULTIPLIER,
    DIMENSION_COST,
    DIMENSION_WEIGHT,
    LEGITIMACY_DIMENSIONS,
)


def _confidence_safe(s: pd.Series) -> pd.Series:
    return s.fillna(0.5).clip(lower=0.0, upper=1.0)


def actor_impact_table(signals_df: pd.DataFrame, *, now: Optional[datetime] = None) -> pd.DataFrame:
    cols = [
        "actor_slug", "impact", "credibility", "momentum", "diversity", "authority",
        "cheap_talk_ratio", "high_cost", "low_cost", "signal_count",
        "signal_count_this_week", "signal_count_prev_week",
    ]
    if signals_df.empty:
        return pd.DataFrame(columns=cols)

    df = signals_df.copy()
    df["confidence"] = _confidence_safe(df["confidence"])
    df["dim_weight"] = df["dimension"].map(DIMENSION_WEIGHT).fillna(0.8)
    df["weighted"] = df["dim_weight"] * df["confidence"]
    df["cost_mult"] = df["dimension"].map(lambda d: COST_MULTIPLIER.get(DIMENSION_COST.get(d, "medium"), 0.7))
    df["credibility_weighted"] = df["weighted"] * df["cost_mult"]
    df["is_capability"] = df["dimension"].isin(CAPABILITY_DIMENSIONS)
    df["is_legitimacy"] = df["dimension"].isin(LEGITIMACY_DIMENSIONS)
    df["is_high_cost"] = df["dimension"].map(lambda d: DIMENSION_COST.get(d, "medium") == "high")
    df["is_low_cost"] = df["dimension"].map(lambda d: DIMENSION_COST.get(d, "medium") == "low")

    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    df["inserted_at_dt"] = pd.to_datetime(df["inserted_at"], utc=True, errors="coerce")
    df["is_this_week"] = df["inserted_at_dt"] >= week_ago
    df["is_prev_week"] = (df["inserted_at_dt"] < week_ago) & (df["inserted_at_dt"] >= two_weeks_ago)

    grouped = df.groupby("actor_slug", as_index=False).agg(
        impact=("weighted", "sum"),
        credibility=("credibility_weighted", "sum"),
        signal_count=("dimension", "count"),
        diversity=("dimension", "nunique"),
        capability=("is_capability", "sum"),
        legitimacy=("is_legitimacy", "sum"),
        high_cost=("is_high_cost", "sum"),
        low_cost=("is_low_cost", "sum"),
        signal_count_this_week=("is_this_week", "sum"),
        signal_count_prev_week=("is_prev_week", "sum"),
    )

    grouped["impact"] = grouped["impact"].round(2)
    grouped["credibility"] = grouped["credibility"].round(2)
    grouped["authority"] = (
        (grouped["capability"] + 1) / (grouped["capability"] + grouped["legitimacy"] + 2)
    ).round(3)
    grouped["cheap_talk_ratio"] = (grouped["low_cost"] / grouped["signal_count"].clip(lower=1)).round(3)
    grouped["momentum"] = grouped["signal_count_this_week"].astype(int) - grouped["signal_count_prev_week"].astype(int)

    return grouped[cols].sort_values("impact", ascending=False)


def attach_actor_metadata(scores_df: pd.DataFrame, actors_df: pd.DataFrame) -> pd.DataFrame:
    if scores_df.empty:
        return scores_df.assign(name=None, category=None, homepage=None)
    cols = ["slug", "name", "category", "homepage"]
    have = [c for c in cols if c in actors_df.columns] if not actors_df.empty else []
    if not have:
        return scores_df.assign(name=scores_df["actor_slug"], category=None, homepage=None)
    return scores_df.merge(
        actors_df[have].rename(columns={"slug": "actor_slug"}),
        on="actor_slug", how="left",
    )


def ecosystem_summary(scores_df: pd.DataFrame) -> dict:
    if scores_df.empty:
        return {
            "n_actors_with_signals": 0, "total_impact": 0.0, "total_credibility": 0.0,
            "total_momentum": 0, "top_actor": None, "top_actor_impact": 0.0,
        }
    top = scores_df.iloc[0]
    return {
        "n_actors_with_signals": int(len(scores_df)),
        "total_impact": float(scores_df["impact"].sum()),
        "total_credibility": float(scores_df["credibility"].sum()) if "credibility" in scores_df else 0.0,
        "total_momentum": int(scores_df["momentum"].sum()),
        "top_actor": top["actor_slug"],
        "top_actor_impact": float(top["impact"]),
    }
