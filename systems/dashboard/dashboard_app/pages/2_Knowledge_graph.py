"""Knowledge graph view — actors, dimensions, co-occurrence."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from dashboard_app import data_access as da
from dashboard_app.knowledge_graph import build_graph, render_html


st.set_page_config(page_title="Knowledge graph", layout="wide")
st.title("Knowledge graph")
st.caption(
    "Actors are coloured by category; size grows with the number of distinct dimensions they've signalled on. "
    "Light-grey nodes are signal dimensions. Actor-to-actor edges appear when two actors share at least N dimensions."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

signals_df = da.signals(days=days)
if system:
    signals_df = signals_df[signals_df["system"] == system]

actors_df = da.actors()

threshold = st.slider("Min shared dimensions for actor-actor edge", min_value=1, max_value=5, value=2)

if signals_df.empty:
    st.info("Nothing to graph yet — no signals in the current window.")
    st.stop()

g = build_graph(signals_df, actors_df, shared_dim_threshold=threshold)
st.caption(f"{g.number_of_nodes()} nodes · {g.number_of_edges()} edges")

html = render_html(g, height="700px")
components.html(html, height=750, scrolling=False)
