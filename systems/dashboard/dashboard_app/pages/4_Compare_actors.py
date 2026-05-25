"""Head-to-head — pick two actors, see them side-by-side."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata


st.set_page_config(page_title="Compare two actors", layout="wide", page_icon="⚖️")
st.title("⚖️ Compare two actors")
st.caption(
    "Useful for: 'how does this startup stack up against this university hub?', "
    "'are these two competitors really different?', or 'pick the right partner'."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

actors_df = da.actors()
signals_df = da.signals(system=system, days=days)
if actors_df.empty or signals_df.empty:
    st.info("Not enough data yet to compare actors.")
    st.stop()

scores = attach_actor_metadata(actor_impact_table(signals_df), actors_df)
labels = scores.assign(display=lambda d: d["name"].fillna(d["actor_slug"])).sort_values("display")

c1, c2 = st.columns(2)
left_pick = c1.selectbox("Actor A", options=labels["display"].tolist(), index=0)
default_b_idx = 1 if len(labels) > 1 else 0
right_pick = c2.selectbox("Actor B", options=labels["display"].tolist(), index=default_b_idx)

if left_pick == right_pick:
    st.warning("Pick two different actors.")
    st.stop()

a = labels[labels["display"] == left_pick].iloc[0]
b = labels[labels["display"] == right_pick].iloc[0]

# ---------- Score grid ----------
st.markdown("### Scorecard")
def _card(col, row):
    with col:
        st.markdown(f"#### {row['display']}")
        st.caption(L.category(row.get("category", "")) if row.get("category") else "")
        s1, s2 = st.columns(2)
        s1.metric("Impact", f"{row['impact']:.2f}")
        s2.metric("Momentum", f"{row['momentum']:+d}")
        s3, s4 = st.columns(2)
        s3.metric("Dimensions", f"{row['diversity']} / 9")
        s4.metric("Authority", f"{row['authority']:.2f}")

cc1, cc2 = st.columns(2)
_card(cc1, a)
_card(cc2, b)

st.markdown("---")

# ---------- Dimension comparison ----------
st.markdown("### Where each actor is loud")
both_sigs = signals_df[signals_df["actor_slug"].isin([a["actor_slug"], b["actor_slug"]])].copy()
both_sigs["actor_name"] = both_sigs["actor_slug"].map({a["actor_slug"]: a["display"], b["actor_slug"]: b["display"]})
both_sigs["dim_label"] = both_sigs["dimension"].map(L.dimension)

mix = both_sigs.groupby(["actor_name", "dim_label"]).size().reset_index(name="count")

chart = (
    alt.Chart(mix)
    .mark_bar()
    .encode(
        x=alt.X("count:Q", title="Signals"),
        y=alt.Y("dim_label:N", sort=alt.SortField(field="count", order="descending"), title=None),
        color=alt.Color("actor_name:N", title="Actor"),
        yOffset=alt.YOffset("actor_name:N"),
        tooltip=["actor_name:N", "dim_label:N", "count:Q"],
    )
    .properties(height=380)
)
st.altair_chart(chart, use_container_width=True)

# ---------- Overlap / divergence ----------
st.markdown("### Shared and unique signal types")
a_dims = set(both_sigs[both_sigs["actor_slug"] == a["actor_slug"]]["dimension"].unique())
b_dims = set(both_sigs[both_sigs["actor_slug"] == b["actor_slug"]]["dimension"].unique())
shared = a_dims & b_dims
only_a = a_dims - b_dims
only_b = b_dims - a_dims

oc1, oc2, oc3 = st.columns(3)
with oc1:
    st.markdown(f"**Both** ({len(shared)})")
    for d in sorted(shared):
        st.markdown(f"- {L.dimension(d)}")
    if not shared:
        st.markdown("_None_")
with oc2:
    st.markdown(f"**Only {a['display']}** ({len(only_a)})")
    for d in sorted(only_a):
        st.markdown(f"- {L.dimension(d)}")
    if not only_a:
        st.markdown("_None_")
with oc3:
    st.markdown(f"**Only {b['display']}** ({len(only_b)})")
    for d in sorted(only_b):
        st.markdown(f"- {L.dimension(d)}")
    if not only_b:
        st.markdown("_None_")
