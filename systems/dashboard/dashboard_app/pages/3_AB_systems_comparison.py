"""System A (MASFactory) vs System B (Hermes) — head-to-head comparison.

This is the empirical-validation page of the thesis: same task, same actors,
same OpenRouter key, two architectures. The interesting question is *not*
which one is "better" — it's where and why they disagree.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L
from dashboard_app.scoring import actor_impact_table, attach_actor_metadata


st.set_page_config(page_title="System A vs System B", layout="wide", page_icon="🆚")
st.title("🆚 System A vs System B")
st.caption(
    "Both systems read the same Swiss-quantum-ecosystem ground truth and write to the same "
    "Supabase tables. Their **divergence** is the thesis's primary empirical finding — "
    "agreement is a quality check, disagreement is data."
)

days = st.session_state.get("filter_days", 30)

# Pull everything (no system filter — we need both)
signals_df = da.signals(system=None, days=days)
runs_df = da.runs(system=None, days=days)
tokens_df = da.token_usage(system=None, days=days)
actors_df = da.actors()

if signals_df.empty:
    st.info("No signals in the current window yet. Open Home and widen the time window.")
    st.stop()

# ---------- Top-line: per-system snapshot ----------
st.markdown("### Snapshot")

def _per_sys_summary(sys_: str) -> dict:
    s_runs = runs_df[runs_df["system"] == sys_] if not runs_df.empty else pd.DataFrame()
    s_signals = signals_df[signals_df["system"] == sys_] if "system" in signals_df.columns else pd.DataFrame()
    s_tokens = tokens_df[tokens_df["system"] == sys_] if not tokens_df.empty else pd.DataFrame()
    return {
        "runs": int(len(s_runs)),
        "ok": int((s_runs["status"] == "ok").sum()) if not s_runs.empty else 0,
        "errors": int((s_runs["status"] == "error").sum()) if not s_runs.empty else 0,
        "signals": int(len(s_signals)),
        "actors": int(s_signals["actor_slug"].nunique()) if not s_signals.empty else 0,
        "input_tokens": int(s_tokens["input_tokens"].sum()) if not s_tokens.empty else 0,
        "output_tokens": int(s_tokens["output_tokens"].sum()) if not s_tokens.empty else 0,
    }

a_sum = _per_sys_summary("masfactory")
b_sum = _per_sys_summary("hermes")

snap = pd.DataFrame(
    [
        {"Metric": "Runs (ok / errors)", "System A · MASFactory": f"{a_sum['ok']} / {a_sum['errors']}", "System B · Hermes": f"{b_sum['ok']} / {b_sum['errors']}"},
        {"Metric": "Signals collected", "System A · MASFactory": f"{a_sum['signals']:,}", "System B · Hermes": f"{b_sum['signals']:,}"},
        {"Metric": "Distinct actors reached", "System A · MASFactory": f"{a_sum['actors']} / {len(actors_df)}", "System B · Hermes": f"{b_sum['actors']} / {len(actors_df)}"},
        {"Metric": "Tokens — input", "System A · MASFactory": f"{a_sum['input_tokens']:,}", "System B · Hermes": f"{b_sum['input_tokens']:,}"},
        {"Metric": "Tokens — output", "System A · MASFactory": f"{a_sum['output_tokens']:,}", "System B · Hermes": f"{b_sum['output_tokens']:,}"},
        {
            "Metric": "Signals per 1k tokens (efficiency)",
            "System A · MASFactory": (
                f"{a_sum['signals'] / max(1, (a_sum['input_tokens']+a_sum['output_tokens'])/1000):.2f}"
                if (a_sum['input_tokens']+a_sum['output_tokens']) else "—"
            ),
            "System B · Hermes": (
                f"{b_sum['signals'] / max(1, (b_sum['input_tokens']+b_sum['output_tokens'])/1000):.2f}"
                if (b_sum['input_tokens']+b_sum['output_tokens']) else "—"
            ),
        },
    ]
)
st.dataframe(snap, use_container_width=True, hide_index=True)

st.markdown("---")

# ---------- Dimension mix per system ----------
st.markdown("### Signal-type mix per system")
st.caption(
    "Do the two systems find different *kinds* of signals? A symmetric distribution would "
    "support the claim that they read the same underlying reality."
)

if "system" not in signals_df.columns:
    st.warning("Signals don't carry the `system` column — older rows from before the schema migration.")
else:
    dim_mix = (
        signals_df.assign(dim_label=signals_df["dimension"].map(L.dimension))
        .assign(sys_label=signals_df["system"].map(L.system_short_label))
        .groupby(["sys_label", "dim_label"]).size().reset_index(name="count")
    )
    if not dim_mix.empty:
        chart = (
            alt.Chart(dim_mix)
            .mark_bar()
            .encode(
                x=alt.X("count:Q", title="Signals"),
                y=alt.Y("dim_label:N", sort="-x", title=None),
                color=alt.Color("sys_label:N", title="System"),
                yOffset=alt.YOffset("sys_label:N"),
                tooltip=["sys_label:N", "dim_label:N", "count:Q"],
            )
            .properties(height=380)
        )
        st.altair_chart(chart, use_container_width=True)

st.markdown("---")

# ---------- Actor overlap ----------
st.markdown("### Where do the two systems agree on which actors matter?")
st.caption(
    "Each system independently computes an Impact score. Agreement = an actor that both "
    "systems flagged with non-trivial impact. Divergence = an actor only one system saw."
)

a_signals = signals_df[signals_df["system"] == "masfactory"] if "system" in signals_df.columns else pd.DataFrame()
b_signals = signals_df[signals_df["system"] == "hermes"] if "system" in signals_df.columns else pd.DataFrame()

a_scores = attach_actor_metadata(actor_impact_table(a_signals), actors_df) if not a_signals.empty else pd.DataFrame()
b_scores = attach_actor_metadata(actor_impact_table(b_signals), actors_df) if not b_signals.empty else pd.DataFrame()

actor_label = dict(zip(actors_df["slug"], actors_df["name"])) if not actors_df.empty else {}

a_map = dict(zip(a_scores["actor_slug"], a_scores["impact"])) if not a_scores.empty else {}
b_map = dict(zip(b_scores["actor_slug"], b_scores["impact"])) if not b_scores.empty else {}
all_slugs = sorted(set(a_map) | set(b_map))

overlap_rows = []
for slug in all_slugs:
    a_imp = a_map.get(slug, 0.0)
    b_imp = b_map.get(slug, 0.0)
    if a_imp == 0 and b_imp == 0:
        continue
    if a_imp > 0 and b_imp > 0:
        verdict = "Both systems"
    elif a_imp > 0:
        verdict = "Only System A"
    else:
        verdict = "Only System B"
    overlap_rows.append(
        {"Actor": actor_label.get(slug, slug), "System A impact": round(a_imp, 2), "System B impact": round(b_imp, 2), "Status": verdict}
    )

if overlap_rows:
    overlap_df = pd.DataFrame(overlap_rows).sort_values("System A impact", ascending=False)
    st.dataframe(
        overlap_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn("Status", help="Whether the actor was reached by both systems or only one."),
        },
    )

    # Quick summary
    n_both = int((overlap_df["Status"] == "Both systems").sum())
    n_a = int((overlap_df["Status"] == "Only System A").sum())
    n_b = int((overlap_df["Status"] == "Only System B").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Both systems", n_both, help="Actors with signals from BOTH systems (cross-system agreement on relevance).")
    c2.metric("Only System A", n_a)
    c3.metric("Only System B", n_b)
else:
    st.info("Not enough cross-system data yet — both systems need at least one successful run each.")

st.markdown("---")

# ---------- Impact agreement scatter ----------
st.markdown("### Impact agreement per actor")
st.caption("Diagonal = perfect agreement. Points off-diagonal show where the systems disagree on relevance.")
if a_scores.empty or b_scores.empty:
    st.info("Need at least one successful run from each system to plot.")
else:
    cross = pd.DataFrame(
        {
            "actor_slug": all_slugs,
            "name": [actor_label.get(s, s) for s in all_slugs],
            "a_impact": [a_map.get(s, 0.0) for s in all_slugs],
            "b_impact": [b_map.get(s, 0.0) for s in all_slugs],
        }
    )
    chart = (
        alt.Chart(cross)
        .mark_circle(opacity=0.75, size=120)
        .encode(
            x=alt.X("a_impact:Q", title="System A · Impact"),
            y=alt.Y("b_impact:Q", title="System B · Impact"),
            tooltip=[alt.Tooltip("name:N", title="Actor"),
                     alt.Tooltip("a_impact:Q", title="System A impact", format=".2f"),
                     alt.Tooltip("b_impact:Q", title="System B impact", format=".2f")],
        )
        .properties(height=420)
    )
    diag = (
        alt.Chart(
            pd.DataFrame({
                "x": [0, float(max(cross["a_impact"].max(), cross["b_impact"].max()) or 1.0)],
                "y": [0, float(max(cross["a_impact"].max(), cross["b_impact"].max()) or 1.0)],
            })
        )
        .mark_line(color="#aaa", strokeDash=[4, 4])
        .encode(x="x:Q", y="y:Q")
    )
    st.altair_chart(diag + chart, use_container_width=True)

st.markdown("---")

# ---------- Token efficiency ----------
st.markdown("### Cost efficiency (signals per 1k tokens)")
st.caption(
    "The thesis's 'output quality per token cost' metric, simplified. Higher = the system "
    "extracted more signals per token spent on LLM calls."
)
eff = pd.DataFrame(
    [
        {
            "System": L.system_label("masfactory"),
            "Signals": a_sum["signals"],
            "Total tokens": a_sum["input_tokens"] + a_sum["output_tokens"],
            "Signals per 1k tokens": (
                a_sum["signals"] / max(1, (a_sum["input_tokens"] + a_sum["output_tokens"]) / 1000)
            ),
        },
        {
            "System": L.system_label("hermes"),
            "Signals": b_sum["signals"],
            "Total tokens": b_sum["input_tokens"] + b_sum["output_tokens"],
            "Signals per 1k tokens": (
                b_sum["signals"] / max(1, (b_sum["input_tokens"] + b_sum["output_tokens"]) / 1000)
            ),
        },
    ]
)
eff["Signals per 1k tokens"] = eff["Signals per 1k tokens"].round(2)
st.dataframe(eff, use_container_width=True, hide_index=True)

st.caption(
    "Interpretation note: a system that yields fewer but higher-quality signals will look "
    "worse on this raw ratio. Pair with the Methodology page's discussion of recall vs "
    "precision before drawing conclusions."
)
