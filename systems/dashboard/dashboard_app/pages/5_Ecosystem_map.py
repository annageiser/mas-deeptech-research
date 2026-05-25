"""Ecosystem map — category-level view of the Swiss quantum landscape."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata


st.set_page_config(page_title="Ecosystem map", layout="wide", page_icon="🗺️")
st.title("🗺️ Ecosystem map")
st.caption(
    "Where is the action concentrated — universities vs companies, national initiatives vs "
    "ecosystem builders? Drill into a category to see its leaders."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

actors_df = da.actors()
signals_df = da.signals(system=system, days=days)
if actors_df.empty or signals_df.empty:
    st.info("Not enough data yet.")
    st.stop()

scores = attach_actor_metadata(actor_impact_table(signals_df), actors_df)
scores["category_label"] = scores["category"].map(lambda c: L.category(c) if c else "Unknown")
scores["display"] = scores.apply(lambda r: r.get("name") or r["actor_slug"], axis=1)

# ---------- Per-category aggregate ----------
cat_agg = (
    scores.groupby("category_label")
    .agg(
        actors=("actor_slug", "nunique"),
        total_impact=("impact", "sum"),
        total_signals=("signal_count", "sum"),
        avg_diversity=("diversity", "mean"),
        avg_authority=("authority", "mean"),
        net_momentum=("momentum", "sum"),
    )
    .reset_index()
    .sort_values("total_impact", ascending=False)
)
cat_agg["total_impact"] = cat_agg["total_impact"].round(2)
cat_agg["avg_diversity"] = cat_agg["avg_diversity"].round(1)
cat_agg["avg_authority"] = cat_agg["avg_authority"].round(2)

st.markdown("### Categories ranked")
st.dataframe(
    cat_agg.rename(columns={
        "category_label": "Category",
        "actors": "Active actors",
        "total_impact": "Total impact",
        "total_signals": "Signals",
        "avg_diversity": "Avg dimensions",
        "avg_authority": "Avg authority",
        "net_momentum": "Net Δ week",
    }),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Total impact": st.column_config.ProgressColumn(
            "Total impact",
            format="%.2f",
            min_value=0.0,
            max_value=float(cat_agg["total_impact"].max() or 1.0),
        ),
    },
)

st.markdown("---")

# ---------- Treemap-style chart ----------
st.markdown("### Visual landscape")
st.caption("Each rectangle is one actor. Area ∝ impact, colour by category.")
viz = scores.copy()
viz["impact_for_size"] = viz["impact"].clip(lower=0.1)  # avoid zero-area rectangles

chart = (
    alt.Chart(viz)
    .mark_rect(stroke="white", strokeWidth=1)
    .encode(
        x=alt.X("category_label:N", title=None, sort=cat_agg["category_label"].tolist()),
        y=alt.Y("display:N", title=None, sort=alt.SortField(field="impact", order="descending")),
        color=alt.Color("category_label:N", title="Category"),
        opacity=alt.Opacity("impact:Q", scale=alt.Scale(range=[0.3, 1.0])),
        tooltip=[
            alt.Tooltip("display:N", title="Actor"),
            alt.Tooltip("category_label:N", title="Category"),
            alt.Tooltip("impact:Q", title="Impact", format=".2f"),
            alt.Tooltip("signal_count:Q", title="Signals"),
            alt.Tooltip("diversity:Q", title="Dimensions"),
            alt.Tooltip("authority:Q", title="Authority", format=".2f"),
            alt.Tooltip("momentum:Q", title="Momentum"),
        ],
    )
    .properties(height=460)
)
st.altair_chart(chart, use_container_width=True)

st.markdown("---")

# ---------- Per-category leader ----------
st.markdown("### Category leaders")
for cat in cat_agg["category_label"]:
    top_in_cat = scores[scores["category_label"] == cat].sort_values("impact", ascending=False).head(5)
    with st.expander(f"**{cat}** — top {min(5, len(top_in_cat))} by impact"):
        if top_in_cat.empty:
            st.markdown("_no signals in this window_")
            continue
        st.dataframe(
            top_in_cat[["display", "impact", "momentum", "diversity", "authority", "signal_count"]].rename(
                columns={
                    "display": "Actor",
                    "impact": "Impact",
                    "momentum": "Δ week",
                    "diversity": "Dimensions",
                    "authority": "Authority",
                    "signal_count": "Signals",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
