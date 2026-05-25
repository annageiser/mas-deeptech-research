"""Impact leaderboard — who has impact, who's gaining, who's losing.

Four sortable views in one page (tab navigation):
- Impact      : weighted signal score
- Momentum    : signal-count change vs previous 7-day window
- Diversity   : how many distinct signal types the actor has shown
- Authority   : capability evidence vs legitimacy evidence ratio
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata


st.set_page_config(page_title="Impact leaderboard", layout="wide", page_icon="🏆")
st.title("🏆 Impact leaderboard")
st.caption(
    "Four lenses on the same data. Each tab ranks actors by a different facet of "
    "what 'impact' means in a deep-tech market with no prices or share data. "
    "All formulas are documented on the Methodology page."
)

system = st.session_state.get("filter_system")
days = st.session_state.get("filter_days", 30)

signals_df = da.signals(system=system, days=days)
actors_df = da.actors()
if signals_df.empty:
    st.info("No signals in the current window. Open Home to widen the time window.")
    st.stop()

scores = attach_actor_metadata(actor_impact_table(signals_df), actors_df)
scores["display"] = scores.apply(lambda r: r.get("name") or r["actor_slug"], axis=1)
scores["category_pretty"] = scores["category"].map(lambda c: L.category(c) if c else "—")


def _render_table(view: pd.DataFrame, score_col: str, score_help: str, fmt: str = "%.2f", show_progress: bool = True):
    # `score_col` is one of momentum / diversity / signal_count / impact / authority.
    # Build the column list deduped, in display order, with the score column always second-from-left.
    base = ["display", "category_pretty", score_col, "signal_count", "diversity", "momentum"]
    seen: set[str] = set()
    cols = [c for c in base if not (c in seen or seen.add(c))]
    score_label = {
        "impact": "Impact",
        "momentum": "Δ week",
        "diversity": "Dimensions",
        "authority": "Authority",
        "signal_count": "Signals",
    }.get(score_col, score_col.title().replace("_", " "))
    pretty = {
        "display": "Actor",
        "category_pretty": "Category",
        score_col: score_label,
        "signal_count": "Signals",
        "diversity": "Dimensions",
        "momentum": "Δ week",
    }
    cfg = {
        "Signals": st.column_config.NumberColumn("Signals"),
        "Dimensions": st.column_config.NumberColumn("Dimensions", help="Number of distinct signal types out of 9."),
        "Δ week": st.column_config.NumberColumn("Δ week", help="Signal-count change vs previous 7-day window."),
    }
    if show_progress and not view.empty and view[score_col].max() > 0:
        cfg[pretty[score_col]] = st.column_config.ProgressColumn(
            pretty[score_col],
            help=score_help,
            format=fmt,
            min_value=0.0,
            max_value=float(view[score_col].max()),
        )
    else:
        cfg[pretty[score_col]] = st.column_config.NumberColumn(pretty[score_col], help=score_help, format=fmt)
    st.dataframe(
        view[cols].rename(columns=pretty),
        use_container_width=True,
        hide_index=True,
        column_config=cfg,
    )


tab_impact, tab_momentum, tab_diversity, tab_authority = st.tabs(
    ["Impact", "Momentum", "Diversity", "Authority (capability vs legitimacy)"]
)

with tab_impact:
    st.markdown("**Impact** = Σ (dimension_weight × confidence) across all signals in the window.")
    st.caption(
        "Heavier weights for funding, patents, technical capability and infrastructure; lighter "
        "weights for market positioning. Reflects how much an external observer would update their "
        "view from the signals seen."
    )
    view = scores.sort_values("impact", ascending=False)
    _render_table(view, "impact", "Weighted signal sum — the headline impact score.")

with tab_momentum:
    st.markdown("**Momentum** = signal count this week − signal count previous week.")
    st.caption("Positive values mean the actor is accelerating; negative means cooling.")
    view = scores.sort_values("momentum", ascending=False)
    _render_table(view, "momentum", "Net change in number of signals vs previous 7-day window.", fmt="%d", show_progress=False)

with tab_diversity:
    st.markdown("**Diversity** = number of distinct signal types observed (max 9).")
    st.caption(
        "An actor that only ever signals about funding looks different from one signalling "
        "across research, partnerships, hiring, and IP — even if the headline counts match."
    )
    view = scores.sort_values("diversity", ascending=False)
    _render_table(view, "diversity", "Distinct dimensions observed for this actor.", fmt="%d", show_progress=True)

with tab_authority:
    st.markdown(
        "**Authority** = capability_signals / (capability + legitimacy). "
        "1.0 = pure capability evidence (research, IP, infra). 0.0 = pure legitimacy evidence "
        "(partnerships, funding, positioning)."
    )
    st.caption(
        "Capability vs legitimacy is the disposition's two-channel framing for deep-tech signalling "
        "(Suchman 1995; Knight & Cavusgil 2004; Ehrenthal et al. 2026). Most healthy actors sit "
        "between 0.3 and 0.7."
    )
    view = scores.sort_values("authority", ascending=False)
    _render_table(view, "authority", "Capability share of total signals. Higher = more deep-tech-output-driven.", fmt="%.2f")

st.markdown("---")

# Visual — impact vs momentum scatter
st.markdown("### 🌐 Impact vs momentum (where each actor sits)")
st.caption(
    "Top-right quadrant = strong + accelerating. Bottom-right = strong but cooling. "
    "Top-left = small but on the rise. Hover for actor name."
)
chart_df = scores.copy()
chart_df["category_pretty"] = chart_df["category"].map(lambda c: L.category(c) if c else "—")
chart = (
    alt.Chart(chart_df)
    .mark_circle(opacity=0.7)
    .encode(
        x=alt.X("impact:Q", title="Impact (this window)"),
        y=alt.Y("momentum:Q", title="Momentum (Δ vs prev week)"),
        size=alt.Size("signal_count:Q", title="Signals", scale=alt.Scale(range=[40, 600])),
        color=alt.Color("category_pretty:N", title="Category"),
        tooltip=[
            alt.Tooltip("display:N", title="Actor"),
            alt.Tooltip("category_pretty:N", title="Category"),
            alt.Tooltip("impact:Q", title="Impact", format=".2f"),
            alt.Tooltip("momentum:Q", title="Momentum"),
            alt.Tooltip("diversity:Q", title="Dimensions"),
            alt.Tooltip("authority:Q", title="Authority", format=".2f"),
            alt.Tooltip("signal_count:Q", title="Signals"),
        ],
    )
    .properties(height=420)
)
st.altair_chart(chart, use_container_width=True)
