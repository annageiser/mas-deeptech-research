"""Signals explorer — filterable table with evidence quotes."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard_app import data_access as da


st.set_page_config(page_title="Signals explorer", layout="wide")
st.title("Signals explorer")

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

signals_df = da.signals(days=days)
if system:
    signals_df = signals_df[signals_df["system"] == system]

if signals_df.empty:
    st.info("No signals in the current window/filter. Adjust the sidebar filters on the Home page.")
    st.stop()

actors_df = da.actors()
actor_name_by_slug = dict(zip(actors_df["slug"], actors_df["name"])) if not actors_df.empty else {}
signals_df["actor"] = signals_df["actor_slug"].map(lambda s: actor_name_by_slug.get(s, s))

col1, col2, col3, col4 = st.columns(4)
sel_actor = col1.multiselect("Actor", sorted(signals_df["actor"].dropna().unique().tolist()))
sel_dim = col2.multiselect("Dimension", sorted(signals_df["dimension"].dropna().unique().tolist()))
sel_kind = col3.multiselect("Source kind", sorted(signals_df["source_kind"].dropna().unique().tolist()))
min_conf = col4.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)

mask = signals_df["confidence"] >= min_conf
if sel_actor:
    mask &= signals_df["actor"].isin(sel_actor)
if sel_dim:
    mask &= signals_df["dimension"].isin(sel_dim)
if sel_kind:
    mask &= signals_df["source_kind"].isin(sel_kind)

view = signals_df[mask][
    ["inserted_at", "system", "actor", "dimension", "is_technical", "confidence", "title", "summary", "evidence_quote", "source_url"]
].sort_values("inserted_at", ascending=False)

st.caption(f"{len(view):,} signals matching")

st.dataframe(
    view,
    use_container_width=True,
    column_config={
        "source_url": st.column_config.LinkColumn("source", display_text="open"),
        "confidence": st.column_config.ProgressColumn("conf", format="%.2f", min_value=0, max_value=1),
        "is_technical": st.column_config.CheckboxColumn("tech"),
        "summary": st.column_config.TextColumn("summary", width="medium"),
        "evidence_quote": st.column_config.TextColumn("evidence", width="medium"),
    },
    hide_index=True,
    height=620,
)

st.download_button(
    "Download as CSV",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name=f"signals_{system or 'both'}_{days}d.csv",
    mime="text/csv",
)
