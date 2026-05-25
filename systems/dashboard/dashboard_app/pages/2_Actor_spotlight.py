"""Actor spotlight — per-actor deep dive.

Pick an actor → see their profile, scores, signal timeline, evidence quotes,
and where they sit relative to peers in the same category.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata


st.set_page_config(page_title="Actor spotlight", layout="wide", page_icon="🔬")
st.title("🔬 Actor spotlight")

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

actors_df = da.actors()
signals_df = da.signals(system=system, days=days)
if actors_df.empty:
    st.info("No actors in the database yet.")
    st.stop()

# Picker
actor_names = actors_df.assign(display=lambda d: d["name"] + " · " + d["category"].map(L.category))
choice = st.selectbox(
    "Pick an actor",
    options=actor_names["display"].tolist(),
    index=0,
    help="The full Swiss quantum-computing actor list.",
)
picked = actors_df.iloc[actor_names.index[actor_names["display"] == choice][0]]

# ---------- Header ----------
top1, top2 = st.columns([0.7, 0.3])
with top1:
    st.markdown(f"## {picked['name']}")
    st.caption(f"_{L.category(picked['category'])}_")
    if picked.get("homepage"):
        st.markdown(f"[Open homepage ↗]({picked['homepage']})")
    if picked.get("arxiv_query"):
        st.markdown(
            f"<span style='color:#888;font-size:0.9em'>arXiv query: <code>{picked['arxiv_query']}</code></span>",
            unsafe_allow_html=True,
        )
    if picked.get("notes"):
        st.markdown(f"> {picked['notes']}")

with top2:
    actor_signals = signals_df[signals_df["actor_slug"] == picked["slug"]] if not signals_df.empty else pd.DataFrame()
    st.metric("Signals in window", f"{len(actor_signals):,}")

if actor_signals.empty:
    st.info(
        "No signals collected for this actor in the current time window. "
        "Try widening the window in the sidebar (Home page) or check whether the actor has an "
        "`arxiv_query` and a homepage configured."
    )
    st.stop()

# ---------- Score panel ----------
scores = attach_actor_metadata(actor_impact_table(signals_df), actors_df)
my_score = scores[scores["actor_slug"] == picked["slug"]].iloc[0]

s1, s2, s3, s4 = st.columns(4)
s1.metric("Impact", f"{my_score['impact']:.2f}", help="Weighted signal sum.")
s2.metric(
    "Momentum",
    f"{my_score['momentum']:+d}",
    delta=f"{my_score['signal_count_this_week']} this wk vs {my_score['signal_count_prev_week']} prev",
)
s3.metric("Dimensions", f"{my_score['diversity']} / 9")
s4.metric(
    "Authority",
    f"{my_score['authority']:.2f}",
    help="Capability share (1.0 = all research/IP/infra; 0.0 = all positioning/partnerships).",
)

# Peer rank within category
peers = scores[scores["category"] == picked["category"]].sort_values("impact", ascending=False).reset_index(drop=True)
if not peers.empty:
    rank = int(peers.index[peers["actor_slug"] == picked["slug"]].tolist()[0]) + 1
    st.caption(
        f"**Rank within {L.category(picked['category'])}:** #{rank} of {len(peers)} (by impact)."
    )

st.markdown("---")

# ---------- Signal-type breakdown ----------
left, right = st.columns([0.5, 0.5], gap="large")
with left:
    st.markdown("### Signal mix")
    mix = (
        actor_signals.assign(dim=actor_signals["dimension"].map(L.dimension))
        .groupby("dim").size().reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    mix_chart = (
        alt.Chart(mix)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Signals"),
            y=alt.Y("dim:N", sort="-x", title=None),
            tooltip=["dim:N", "count:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(mix_chart, use_container_width=True)

with right:
    st.markdown("### Timeline")
    tl = actor_signals.copy()
    tl["day"] = pd.to_datetime(tl["inserted_at"], utc=True, errors="coerce").dt.tz_convert("Europe/Zurich").dt.date
    tl_agg = tl.groupby(["day"]).size().reset_index(name="signals")
    tl_chart = (
        alt.Chart(tl_agg)
        .mark_bar()
        .encode(
            x=alt.X("day:T", title="Date (CET)"),
            y=alt.Y("signals:Q", title="Signals"),
            tooltip=["day:T", "signals:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(tl_chart, use_container_width=True)

st.markdown("---")

# ---------- Evidence list ----------
st.markdown("### Evidence")
st.caption(
    f"All {len(actor_signals)} signals captured for this actor in the window, newest first. "
    "Each one is grounded in a verbatim quote from the source."
)

ev = actor_signals.copy()
ev["dim_label"] = ev["dimension"].map(L.dimension)
ev["when"] = pd.to_datetime(ev["inserted_at"], utc=True, errors="coerce").dt.tz_convert("Europe/Zurich").dt.strftime("%Y-%m-%d %H:%M")
ev["src"] = ev["source_kind"].map(L.source_kind)
ev["type"] = ev["is_technical"].map(L.tech_label)

for _, r in ev.sort_values("inserted_at", ascending=False).iterrows():
    with st.container(border=True):
        a, b = st.columns([0.75, 0.25])
        with a:
            st.markdown(f"**{r['dim_label']}** · _{r['type']}_  · {r['title'] or '(no title)'}")
            if r.get("summary"):
                st.markdown(r["summary"])
            if r.get("evidence_quote"):
                st.markdown(f"> {r['evidence_quote']}")
        with b:
            st.markdown(f"<span style='color:#888;font-size:0.85em'>{r['when']}<br/>"
                        f"{r['src']} · confidence {r['confidence']:.2f}<br/>"
                        f"<a href='{r['source_url']}' target='_blank'>open source ↗</a></span>",
                        unsafe_allow_html=True)
