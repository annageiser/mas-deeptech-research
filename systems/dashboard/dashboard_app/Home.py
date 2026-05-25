"""Stakeholder landing page — Swiss quantum-computing ecosystem at a glance.

Audience: researchers, investors, business advisors. They want a fast read of
the ecosystem in 60 seconds, then a path into deeper drill-down via the
other pages. No DB column names in this UI — see `labels.py`.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import (
    actor_impact_table,
    attach_actor_metadata,
    ecosystem_summary,
)


st.set_page_config(
    page_title="Swiss Quantum Ecosystem · Signal Dashboard",
    page_icon="⚛️",
    layout="wide",
)

st.title("Swiss Quantum Ecosystem · Signal Dashboard")
st.caption(
    "Who has impact in Swiss quantum computing right now, what signals they're sending, "
    "and how their position is shifting week over week — collected automatically from public "
    "sources (arXiv, official websites) every day. "
    "Two independent AI systems harvest the data in parallel so the findings can be cross-checked. "
    "Bachelor Thesis · Anna Geiser · FHNW · supervised by Prof. Dr. J. Ehrenthal."
)

# ---------- Sidebar filters ----------
with st.sidebar:
    st.header("Filters")
    sys_choice = st.selectbox(
        "Data source",
        options=["Both systems (recommended)", L.SYSTEM_LABEL["masfactory"], L.SYSTEM_LABEL["hermes"]],
        index=0,
        help=(
            "The dashboard reads from two independent AI pipelines that scrape the same "
            "ecosystem in parallel. Cross-system agreement is one of the thesis's quality checks. "
            "Use 'Both systems' unless you want to compare the two."
        ),
    )
    system = None
    if sys_choice == L.SYSTEM_LABEL["masfactory"]:
        system = "masfactory"
    elif sys_choice == L.SYSTEM_LABEL["hermes"]:
        system = "hermes"
    st.session_state["filter_system"] = system

    days = st.slider(
        "Time window (days)",
        min_value=7,
        max_value=180,
        value=30,
        step=7,
        help="All metrics on the dashboard are computed over this window.",
    )
    st.session_state["filter_days"] = days

    st.markdown("---")
    st.markdown(
        "**Navigate**\n"
        "- 🏆 Impact leaderboard\n"
        "- 🔬 Actor spotlight\n"
        "- ⚖️ Compare two actors\n"
        "- 🗺️ Ecosystem map\n"
        "- 🕸️ Knowledge graph\n"
        "- 📊 Signals (raw table)\n"
        "- 📄 Reports\n"
        "- 📐 Methodology"
    )

# ---------- Load ----------
signals_df = da.signals(system=system, days=days)
actors_df = da.actors()
runs_df = da.runs(system=system, days=days)

if signals_df.empty:
    st.info(
        "No signals in the current window yet. The system collects daily at "
        "02:00 (System A) and 05:00 (System B) Europe/Zurich. If you just deployed, "
        "wait for tomorrow's run or trigger a manual scrape via SSH."
    )
    st.stop()

scores_df = attach_actor_metadata(actor_impact_table(signals_df), actors_df)
es = ecosystem_summary(scores_df)

# ---------- Hero metrics ----------
n_actors_total = len(actors_df)
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Actors tracked",
    f"{n_actors_total}",
    help="The full Swiss quantum-computing actor list maintained in the database.",
)
c2.metric(
    "Active in this window",
    f"{es['n_actors_with_signals']} / {n_actors_total}",
    help="Actors with at least one signal observed in the selected time window.",
)
c3.metric(
    "New signals collected",
    f"{len(signals_df):,}",
    delta=f"{int(scores_df['signal_count_this_week'].sum())} this week",
    help="Each signal is one piece of public evidence about an actor's position.",
)
c4.metric(
    "Ecosystem momentum",
    f"{es['total_momentum']:+d}",
    help="Signal-count change between this week and the previous week, summed across all actors.",
    delta=f"{es['total_momentum']:+d} vs. prev week",
    delta_color="normal",
)

st.markdown("---")

# ---------- Two columns: Top actors + Recent signals ----------
left, right = st.columns([0.55, 0.45], gap="large")

with left:
    st.markdown("### 🏆 Top actors by impact, this window")
    st.caption(
        "Impact = the weighted sum of all signals, where each dimension carries a weight reflecting "
        "how much it tells a market observer (funding > positioning, etc.). See the Methodology page."
    )
    top_n = min(10, len(scores_df))
    top = scores_df.head(top_n).copy()
    top["display"] = top.apply(lambda r: r.get("name") or r["actor_slug"], axis=1)
    top["category_pretty"] = top["category"].map(lambda c: L.category(c) if c else "—")
    top["momentum_arrow"] = top["momentum"].map(lambda m: "▲" if m > 0 else ("▼" if m < 0 else "·"))

    st.dataframe(
        top[["display", "category_pretty", "impact", "momentum_arrow", "momentum", "signal_count", "diversity"]].rename(
            columns={
                "display": "Actor",
                "category_pretty": "Category",
                "impact": "Impact",
                "momentum_arrow": "",
                "momentum": "Δ week",
                "signal_count": "Signals",
                "diversity": "Dimensions",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Impact": st.column_config.ProgressColumn(
                "Impact",
                help="Weighted signal sum. Higher = louder, more diversely sourced positioning.",
                format="%.2f",
                min_value=0.0,
                max_value=float(top["impact"].max()) if len(top) else 1.0,
            ),
            "Δ week": st.column_config.NumberColumn(
                "Δ week", help="Net change in signal count vs the previous 7-day window."
            ),
            "Dimensions": st.column_config.NumberColumn(
                "Dimensions",
                help=f"Number of distinct signal types this actor has shown. Max 9.",
            ),
        },
    )

with right:
    st.markdown("### ⏱ Latest signals")
    st.caption("The most recent evidence captured by either system.")
    recent = signals_df.copy()
    recent["actor_name"] = recent["actor_slug"].map(
        lambda s: dict(zip(actors_df["slug"], actors_df["name"])).get(s, s) if not actors_df.empty else s
    )
    recent["dim_label"] = recent["dimension"].map(L.dimension)
    recent["when"] = pd.to_datetime(recent["inserted_at"], utc=True, errors="coerce").dt.tz_convert("Europe/Zurich").dt.strftime("%Y-%m-%d %H:%M")

    show_n = min(8, len(recent))
    for _, r in recent.head(show_n).iterrows():
        st.markdown(
            f"**{r['actor_name']}** · _{r['dim_label']}_  \n"
            f"{r.get('summary', '')[:200]}{'…' if len(r.get('summary','')) > 200 else ''}  \n"
            f"<span style='color:#888;font-size:0.85em'>{r['when']} · "
            f"<a href='{r['source_url']}' target='_blank'>source ↗</a></span>",
            unsafe_allow_html=True,
        )
        st.markdown("")

st.markdown("---")

# ---------- Category mix ----------
st.markdown("### 🗺 Where is the signal coming from?")
st.caption("Signal volume by actor category, this window. Click categories on the chart to filter.")

sig_with_meta = signals_df.merge(
    actors_df[["slug", "category"]].rename(columns={"slug": "actor_slug"}),
    on="actor_slug",
    how="left",
)
sig_with_meta["category_label"] = sig_with_meta["category"].map(lambda c: L.category(c) if c else "Unknown")
sig_with_meta["dim_label"] = sig_with_meta["dimension"].map(L.dimension)

cat_chart = (
    alt.Chart(sig_with_meta)
    .mark_bar()
    .encode(
        x=alt.X("count():Q", title="Signals"),
        y=alt.Y("category_label:N", sort="-x", title=None),
        color=alt.Color(
            "dim_label:N",
            title="Signal type",
            scale=alt.Scale(scheme="tableau10"),
        ),
        tooltip=[
            alt.Tooltip("category_label:N", title="Category"),
            alt.Tooltip("dim_label:N", title="Signal type"),
            alt.Tooltip("count():Q", title="Signals"),
        ],
    )
    .properties(height=340)
)
st.altair_chart(cat_chart, use_container_width=True)

st.markdown("---")

# ---------- Cross-system sanity ----------
if system is None and "system" in signals_df.columns:
    st.markdown("### 🔁 Cross-system sanity check")
    st.caption(
        "Both AI systems harvest the same ecosystem independently. The thesis treats the two "
        "as alternative readings, not duplicates — so divergence here is interesting, not wrong."
    )
    per_sys = (
        signals_df.groupby("system")
        .agg(signals=("id", "count"), actors=("actor_slug", "nunique"))
        .reset_index()
    )
    per_sys["system_label"] = per_sys["system"].map(L.system_label)

    runs_per_sys = (
        runs_df.groupby("system").agg(runs=("id", "count")).reset_index()
        if not runs_df.empty
        else pd.DataFrame(columns=["system", "runs"])
    )
    combined = per_sys.merge(runs_per_sys, on="system", how="left").fillna({"runs": 0})
    combined["runs"] = combined["runs"].astype(int)

    st.dataframe(
        combined[["system_label", "runs", "signals", "actors"]].rename(
            columns={
                "system_label": "System",
                "runs": "Runs",
                "signals": "Signals collected",
                "actors": "Distinct actors",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")
st.caption(
    "Data sources: arXiv (research output), actor websites (other signal types). "
    "Updates: every 24 h via cron. Open the Methodology page for the full taxonomy and scoring formulas."
)
