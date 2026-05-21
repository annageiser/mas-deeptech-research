"""Streamlit entry point — Home / Overview.

Run with:
    streamlit run dashboard_app/Home.py --server.port 8501 --server.address 0.0.0.0
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da


st.set_page_config(
    page_title="mas-deeptech-research dashboard",
    page_icon="🔬",
    layout="wide",
)

st.title("Mas-Deeptech-Research · Dashboard")
st.caption(
    "Comparative MAS for the Swiss quantum-computing ecosystem · BSc thesis, Anna Geiser, FHNW. "
    "Read-only view onto Supabase. Cron-driven scrapes land daily at 02:00 (System A) and 05:00 (System B) Europe/Zurich."
)

# Top filters — propagate via session_state to all pages
with st.sidebar:
    st.header("Filters")
    system = st.selectbox(
        "System",
        options=["both", "masfactory", "hermes"],
        index=0,
        help="Restrict all queries to one system (A=masfactory, B=hermes) or compare side-by-side.",
    )
    st.session_state["filter_system"] = None if system == "both" else system
    days = st.slider("Lookback window (days)", min_value=1, max_value=90, value=30)
    st.session_state["filter_days"] = days
    st.markdown("---")
    st.markdown("**Pages**\n\n- Home (this page)\n- Signals explorer\n- Knowledge graph\n- Reports browser")

# ---------- Top-line numbers ----------
runs_df = da.runs(days=days)
signals_df = da.signals(days=days)

if signals_df.empty and runs_df.empty:
    st.warning("No runs or signals in the lookback window. Either the system just started or cron hasn't fired yet.")
    st.stop()


def _scoped(df: pd.DataFrame, sys: str | None) -> pd.DataFrame:
    if df.empty or sys is None:
        return df
    return df[df["system"] == sys]


c1, c2, c3, c4 = st.columns(4)
sys_filter = st.session_state.get("filter_system")
sf_runs = _scoped(runs_df, sys_filter)
sf_signals = _scoped(signals_df, sys_filter)

c1.metric("Runs", len(sf_runs), help="All runs in the lookback window.")
c2.metric(
    "Successful runs",
    int((sf_runs["status"] == "ok").sum()) if not sf_runs.empty else 0,
    delta=f"-{int((sf_runs['status'] == 'error').sum()) if not sf_runs.empty else 0} errors",
    delta_color="inverse",
)
c3.metric("Signals", len(sf_signals))
c4.metric(
    "Actors with ≥1 signal",
    int(sf_signals["actor_slug"].nunique()) if not sf_signals.empty else 0,
    help=f"out of {len(da.actors())} actors in the catalogue.",
)

# ---------- Side-by-side comparison when system='both' ----------
st.markdown("### Per-system snapshot")
per_sys = (
    signals_df.groupby("system")
    .agg(
        signals=("id", "count"),
        actors=("actor_slug", "nunique"),
        technical=("is_technical", lambda s: int(s.sum())),
        avg_confidence=("confidence", "mean"),
    )
    .reset_index()
    if not signals_df.empty
    else pd.DataFrame(columns=["system", "signals", "actors", "technical", "avg_confidence"])
)
if not per_sys.empty:
    per_sys["non_technical"] = per_sys["signals"] - per_sys["technical"]
    per_sys["avg_confidence"] = per_sys["avg_confidence"].round(3)
    st.dataframe(per_sys, use_container_width=True, hide_index=True)

# ---------- Dimension mix ----------
st.markdown("### Signal dimensions")
if not sf_signals.empty:
    dim = sf_signals.groupby(["system", "dimension"]).size().reset_index(name="count")
    chart = (
        alt.Chart(dim)
        .mark_bar()
        .encode(
            x=alt.X("dimension:N", sort="-y"),
            y="count:Q",
            color="system:N",
            tooltip=["system", "dimension", "count"],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No signals in this window — nothing to chart.")

# ---------- Token spend over time ----------
st.markdown("### Token spend over time")
tokens_df = da.token_usage(days=days)
if not tokens_df.empty:
    tokens_df["recorded_at"] = pd.to_datetime(tokens_df["recorded_at"])
    tok_daily = (
        tokens_df.assign(day=tokens_df["recorded_at"].dt.date)
        .groupby(["day", "system"])
        .agg(input=("input_tokens", "sum"), output=("output_tokens", "sum"))
        .reset_index()
    )
    tok_long = tok_daily.melt(
        id_vars=["day", "system"], value_vars=["input", "output"], var_name="kind", value_name="tokens"
    )
    chart = (
        alt.Chart(tok_long)
        .mark_line(point=True)
        .encode(
            x="day:T",
            y="tokens:Q",
            color="system:N",
            strokeDash="kind:N",
            tooltip=["day", "system", "kind", "tokens"],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No token usage rows yet.")

# ---------- Recent errors ----------
errs = runs_df[runs_df["status"] == "error"] if not runs_df.empty else pd.DataFrame()
if not errs.empty:
    st.markdown("### Recent error runs")
    st.dataframe(
        errs[["started_at", "system", "error_message"]].head(10),
        use_container_width=True,
        hide_index=True,
    )
