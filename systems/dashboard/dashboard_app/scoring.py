"""Actor scoring — Impact, Momentum, Diversity, Authority.

Each score is a transparent, reproducible function of the raw signals table.
Methodology is exposed on the Methodology page so stakeholders can audit it.

References (cited on the Methodology page):
- Ehrenthal, Gonzalez-Padron, & Gruen (2026) — noncommensurable performance
  / strategic signalling in quantum-computing vendors
- Suchman (1995) — Managing Legitimacy: Strategic and Institutional Approaches
- Knight & Cavusgil (2004) — Innovation, organisational capabilities
- Mohr & Sarin (2009) — Drucker's insights on market orientation in
  high-technology marketing
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .labels import (
    CAPABILITY_DIMENSIONS,
    DIMENSION_WEIGHT,
    LEGITIMACY_DIMENSIONS,
)


@dataclass(frozen=True)
class ActorScore:
    actor_slug: str
    impact: float
    momentum: float        # > 0 = growing, < 0 = cooling
    diversity: int         # number of distinct dimensions touched
    authority: float       # capability / (capability + legitimacy), 0..1
    signal_count: int
    signal_count_this_week: int
    signal_count_prev_week: int


def _confidence_safe(s: pd.Series) -> pd.Series:
    return s.fillna(0.5).clip(lower=0.0, upper=1.0)


def actor_impact_table(
    signals_df: pd.DataFrame,
    *,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Per-actor score table indexed by actor_slug.

    Impact = Σ_i (dimension_weight_i × confidence_i) over all signals for the actor.
    Momentum = signals_last_7d − signals_prev_7d (raw count delta).
    Diversity = count of distinct dimensions touched.
    Authority = capability_signals / (capability + legitimacy), with a smoothing prior.
    """
    if signals_df.empty:
        return pd.DataFrame(
            columns=[
                "actor_slug",
                "impact",
                "momentum",
                "diversity",
                "authority",
                "signal_count",
                "signal_count_this_week",
                "signal_count_prev_week",
            ]
        )

    df = signals_df.copy()
    df["confidence"] = _confidence_safe(df["confidence"])
    df["dim_weight"] = df["dimension"].map(DIMENSION_WEIGHT).fillna(0.8)
    df["weighted"] = df["dim_weight"] * df["confidence"]
    df["is_capability"] = df["dimension"].isin(CAPABILITY_DIMENSIONS)
    df["is_legitimacy"] = df["dimension"].isin(LEGITIMACY_DIMENSIONS)

    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    df["inserted_at_dt"] = pd.to_datetime(df["inserted_at"], utc=True, errors="coerce")
    df["is_this_week"] = df["inserted_at_dt"] >= week_ago
    df["is_prev_week"] = (df["inserted_at_dt"] < week_ago) & (df["inserted_at_dt"] >= two_weeks_ago)

    grouped = df.groupby("actor_slug", as_index=False).agg(
        impact=("weighted", "sum"),
        signal_count=("dimension", "count"),
        diversity=("dimension", "nunique"),
        capability=("is_capability", "sum"),
        legitimacy=("is_legitimacy", "sum"),
        signal_count_this_week=("is_this_week", "sum"),
        signal_count_prev_week=("is_prev_week", "sum"),
    )

    grouped["impact"] = grouped["impact"].round(2)
    # Authority with Laplace smoothing (+1, +2) so a single-signal actor doesn't blow to 0 or 1.
    grouped["authority"] = (
        (grouped["capability"] + 1) / (grouped["capability"] + grouped["legitimacy"] + 2)
    ).round(3)
    grouped["momentum"] = grouped["signal_count_this_week"].astype(int) - grouped["signal_count_prev_week"].astype(int)

    return grouped[
        [
            "actor_slug",
            "impact",
            "momentum",
            "diversity",
            "authority",
            "signal_count",
            "signal_count_this_week",
            "signal_count_prev_week",
        ]
    ].sort_values("impact", ascending=False)


def attach_actor_metadata(scores_df: pd.DataFrame, actors_df: pd.DataFrame) -> pd.DataFrame:
    """Add `name`, `category`, `homepage` columns by joining on actor_slug."""
    if scores_df.empty:
        return scores_df.assign(name=None, category=None, homepage=None)
    cols = ["slug", "name", "category", "homepage"]
    have = [c for c in cols if c in actors_df.columns] if not actors_df.empty else []
    if not have:
        return scores_df.assign(name=scores_df["actor_slug"], category=None, homepage=None)
    return scores_df.merge(
        actors_df[have].rename(columns={"slug": "actor_slug"}),
        on="actor_slug",
        how="left",
    )


def ecosystem_summary(scores_df: pd.DataFrame) -> dict:
    """Top-line numbers for the landing page hero."""
    if scores_df.empty:
        return {
            "n_actors_with_signals": 0,
            "total_impact": 0.0,
            "total_momentum": 0,
            "top_actor": None,
            "top_actor_impact": 0.0,
        }
    top = scores_df.iloc[0]
    return {
        "n_actors_with_signals": len(scores_df),
        "total_impact": float(scores_df["impact"].sum()),
        "total_momentum": int(scores_df["momentum"].sum()),
        "top_actor": top["actor_slug"],
        "top_actor_impact": float(top["impact"]),
    }
