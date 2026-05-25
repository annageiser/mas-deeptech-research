"""Signals explorer — raw filterable table for power users / auditors."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L


st.set_page_config(page_title="Signals · raw table", layout="wide", page_icon="📊")
st.title("📊 Signals · raw table")
st.caption(
    "Every signal in the current window, filterable. Useful for the supervisor or anyone who "
    "wants to audit the underlying evidence. The other pages aggregate and rank — this page lets "
    "you look at the rows directly."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

signals_df = da.signals(system=system, days=days)
if signals_df.empty:
    st.info("No signals in the current window/filter. Adjust the sidebar filters on the Home page.")
    st.stop()

actors_df = da.actors()
actor_name_by_slug = dict(zip(actors_df["slug"], actors_df["name"])) if not actors_df.empty else {}
signals_df["actor"] = signals_df["actor_slug"].map(lambda s: actor_name_by_slug.get(s, s))
signals_df["dimension_label"] = signals_df["dimension"].map(L.dimension)
signals_df["source_label"] = signals_df["source_kind"].map(L.source_kind)
signals_df["type_label"] = signals_df["is_technical"].map(L.tech_label)
signals_df["system_label"] = signals_df["system"].map(L.system_label) if "system" in signals_df.columns else "—"

col1, col2, col3, col4 = st.columns(4)
sel_actor = col1.multiselect("Actor", sorted(signals_df["actor"].dropna().unique().tolist()))
sel_dim = col2.multiselect("Signal type", sorted(signals_df["dimension_label"].dropna().unique().tolist()))
sel_src = col3.multiselect("Source", sorted(signals_df["source_label"].dropna().unique().tolist()))
min_conf = col4.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)

mask = signals_df["confidence"] >= min_conf
if sel_actor:
    mask &= signals_df["actor"].isin(sel_actor)
if sel_dim:
    mask &= signals_df["dimension_label"].isin(sel_dim)
if sel_src:
    mask &= signals_df["source_label"].isin(sel_src)

view = signals_df[mask][
    ["inserted_at", "system_label", "actor", "dimension_label", "type_label", "confidence",
     "title", "summary", "evidence_quote", "source_label", "source_url"]
].sort_values("inserted_at", ascending=False).rename(
    columns={
        "inserted_at": "When",
        "system_label": "Collected by",
        "actor": "Actor",
        "dimension_label": "Signal type",
        "type_label": "Capability / legitimacy",
        "confidence": "Confidence",
        "title": "Headline",
        "summary": "Summary",
        "evidence_quote": "Evidence (verbatim)",
        "source_label": "Source",
        "source_url": "URL",
    }
)

st.caption(f"{len(view):,} signals matching")

st.dataframe(
    view,
    use_container_width=True,
    column_config={
        "URL": st.column_config.LinkColumn("URL", display_text="open ↗"),
        "Confidence": st.column_config.ProgressColumn("Confidence", format="%.2f", min_value=0, max_value=1),
        "Summary": st.column_config.TextColumn("Summary", width="medium"),
        "Evidence (verbatim)": st.column_config.TextColumn("Evidence (verbatim)", width="medium"),
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
