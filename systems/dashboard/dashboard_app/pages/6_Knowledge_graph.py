"""Knowledge graph — actors connected to their signal types, peers via shared signals."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.knowledge_graph import build_graph, render_html


st.set_page_config(page_title="Knowledge graph", layout="wide", page_icon="🕸️")
st.title("🕸️ Knowledge graph")
st.caption(
    "Each large coloured node is an **actor** (colour = category, size grows with the number "
    "of distinct signal types). Each small grey node is a **signal type**. An edge between two "
    "actors appears when they have signalled on at least N of the same types — a rough proxy "
    "for who's playing on the same field."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

signals_df = da.signals(system=system, days=days)
actors_df = da.actors()

threshold = st.slider(
    "Min shared signal types for actor-actor edge",
    min_value=1,
    max_value=5,
    value=2,
    help="Raise to see only the strongest co-positioning relationships.",
)

if signals_df.empty:
    st.info("Nothing to graph yet — no signals in the current window.")
    st.stop()

# Pre-map dimensions to friendly labels before sending to the graph builder.
signals_for_graph = signals_df.copy()
signals_for_graph["dimension"] = signals_for_graph["dimension"].map(lambda d: L.dimension(d) if d else d)

g = build_graph(signals_for_graph, actors_df, shared_dim_threshold=threshold)
st.caption(f"{g.number_of_nodes()} nodes · {g.number_of_edges()} edges")

with st.expander("Legend"):
    cols = st.columns(len(L.CATEGORY_LABEL))
    for col, (cat_key, cat_label) in zip(cols, L.CATEGORY_LABEL.items()):
        col.markdown(
            f"<span style='display:inline-block;width:12px;height:12px;background:{L.CATEGORY_COLOR[cat_key]};border-radius:6px'></span> {cat_label}",
            unsafe_allow_html=True,
        )

html = render_html(g, height="700px")
components.html(html, height=750, scrolling=False)
