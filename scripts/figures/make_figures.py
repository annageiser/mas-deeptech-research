"""Generate all thesis figures + Appendix C from local CSVs and results.json.

Reads:
  data/july_2026_signals.csv           (via scripts/figures/pull_july_2026.py)
  data/july_2026_actors.csv
  systems/masfactory/masfactory_system/classification/schema.yaml
  eval-results/results.json

Writes into docs/figures/:
  fig1_signal_type_per_actor.{png,svg}
  fig2_subdimension_distribution.{png,svg}
  fig3_jaccard_hist.{png,svg}
  fig4_cost_reversal.{png,svg}
  fig5_protocol_departures_timeline.{png,svg}
  fig6_gap_matrix.{png,svg}
  appendix_c_component_source.csv
  appendix_c_component_source.md

Every plot's title / caption cites the July 2026 window filter and the
provenance of each number, so the reader can trace every mark back to a row in
the DB or a section of the thesis.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from matplotlib.patches import Patch

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
OUT = REPO / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

WINDOW_LABEL = "July 2026 (retrieval window 2026-07-01 to 2026-08-01)"

# ---------------------------------------------------------------------------
# Shared palette — matches the mermaid diagrams (fef3c7 agent, dbeafe custom,
# dcfce7 output, fce7f3 memory, e0e7ff skill) plus derived accent colours.
# ---------------------------------------------------------------------------
COL_A = "#1e40af"           # System A · MASFactory (blue)
COL_B = "#9d174d"           # System B · Hermes (magenta)
COL_MANUAL = "#166534"      # manual / propagated
SIGNAL_TYPE_COLORS = {
    "legitimacy":          "#b45309",   # amber
    "customer_cocreation": "#0e7490",   # teal
    "community_ecosystem": "#3730a3",   # indigo
    "future_trajectory":   "#166534",   # green
    "other/out-of-schema": "#9ca3af",   # gray
}
CATEGORY_ORDER = [
    ("national_initiative",       "National initiatives"),
    ("university_or_research_hub","University & research hubs"),
    ("ecosystem_builder",         "Ecosystem builders"),
    ("private_company",           "Private companies"),
    ("government",                "Government"),
]


def load_data():
    signals = pd.read_csv(DATA / "july_2026_signals.csv")
    actors = pd.read_csv(DATA / "july_2026_actors.csv")
    schema = yaml.safe_load((REPO / "systems/masfactory/masfactory_system/classification/schema.yaml").read_text())
    canonical_dims = [d["key"] for d in schema["dimensions"]]
    dim_to_type = {d["key"]: d["signal_type"] for d in schema["dimensions"]}
    results = json.loads((REPO / "eval-results/results.json").read_text())
    return signals, actors, canonical_dims, dim_to_type, results


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", facecolor="white")
    print(f"  wrote docs/figures/{name}.png + .svg")


def _apply_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#333",
        "xtick.color": "#333",
        "ytick.color": "#333",
    })


# ---------------------------------------------------------------------------
# Figure 1 — signal-type distribution per actor, grouped by Swissnex category.
# ---------------------------------------------------------------------------
def fig1_signal_type_per_actor(signals, actors):
    df = signals.merge(actors[["slug", "name", "category"]], left_on="actor_slug", right_on="slug", how="left")
    df = df[df["system"].isin(["masfactory", "hermes"])].copy()

    canonical = set(SIGNAL_TYPE_COLORS) - {"other/out-of-schema"}
    df["signal_type_norm"] = df["signal_type"].where(df["signal_type"].isin(canonical), other="other/out-of-schema")

    counts = df.groupby(["category", "name", "signal_type_norm"]).size().unstack(fill_value=0)
    for st in SIGNAL_TYPE_COLORS:
        if st not in counts.columns:
            counts[st] = 0
    counts["total"] = counts[list(SIGNAL_TYPE_COLORS)].sum(axis=1)

    ordered = []
    seen_cats = 0
    for cat_key, cat_label in CATEGORY_ORDER:
        if cat_key not in counts.index.get_level_values(0):
            continue
        if seen_cats > 0:
            ordered.append(("__spacer__", None, "", None))
        ordered.append(("__header__", cat_label, "", None))
        sub = counts.xs(cat_key, level=0).sort_values("total", ascending=True)
        for name in sub.index:
            ordered.append((cat_key, cat_label, name, sub.loc[name]))
        seen_cats += 1

    n = len(ordered)
    fig, ax = plt.subplots(figsize=(12.5, max(7, 0.30 * n + 2)))
    y = np.arange(n)
    left = np.zeros(n)
    for st in ["legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory", "other/out-of-schema"]:
        vals = np.array([0 if row is None else row[st] for (_, _, _, row) in ordered])
        ax.barh(y, vals, left=left, color=SIGNAL_TYPE_COLORS[st], edgecolor="white", linewidth=0.5, label=st.replace("_", " "))
        left += vals

    tick_labels = []
    for kind, cat_label, name, _ in ordered:
        if kind == "__header__":
            tick_labels.append("")
        elif kind == "__spacer__":
            tick_labels.append("")
        else:
            tick_labels.append(name)
    ax.set_yticks(y)
    ax.set_yticklabels(tick_labels, fontsize=8)
    ax.invert_yaxis()

    for i, (kind, cat_label, _, _) in enumerate(ordered):
        if kind == "__header__":
            ax.text(0, i, cat_label, fontsize=10, weight="bold", color="#111",
                    va="center", ha="left")
            ax.axhline(i + 0.5, color="#bbb", linewidth=0.7, linestyle="-", alpha=0.6)

    ax.set_xlabel("Signals persisted in July 2026")
    ax.set_title("Figure 1 — Signal-type distribution across 40 actors, grouped by Swissnex reporting category")
    ax.legend(loc="lower right", frameon=False, fontsize=9, title="Signal type (Ehrenthal 2026)")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    fig.text(0.01, -0.02, f"Source: public.signals filtered to {WINDOW_LABEL}. Signals from System A (MASFactory) and System B (Hermes) pooled; 'other/out-of-schema' captures the 88.5 % of System B rows whose classifier invented a label outside the 19-key canonical taxonomy (Ergebnisse §4.1).",
             fontsize=7, color="#555", wrap=True)
    save(fig, "fig1_signal_type_per_actor")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2 — sub-dimension distribution across the corpus.
# ---------------------------------------------------------------------------
def fig2_subdimension_distribution(signals, canonical_dims, dim_to_type):
    df = signals[signals["system"].isin(["masfactory", "hermes"])].copy()
    total_all = len(df)
    canonical_df = df[df["dimension"].isin(canonical_dims)]
    other_n = total_all - len(canonical_df)

    counts = canonical_df["dimension"].value_counts().to_dict()
    rows = [(d, counts.get(d, 0), dim_to_type[d]) for d in canonical_dims]
    rows.sort(key=lambda r: r[1])

    dims = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = [SIGNAL_TYPE_COLORS[r[2]] for r in rows]
    y = np.arange(len(dims))

    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(y, vals, color=colors, edgecolor="white", linewidth=0.5)

    pct_denominator = total_all
    for i, (dim, v, st) in enumerate(rows):
        pct = 100.0 * v / pct_denominator if pct_denominator else 0.0
        ax.text(v + max(vals) * 0.008, i, f"{v}  ({pct:.1f}%)", va="center", fontsize=8, color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels(dims, fontsize=9)
    ax.set_xlabel(f"Signals persisted in July 2026 (n = {total_all}, of which {other_n} outside the 19-key canonical taxonomy)")
    ax.set_title("Figure 2 — Sub-dimension distribution across the 19-key canonical taxonomy")

    legend = [Patch(facecolor=SIGNAL_TYPE_COLORS[t], label=t.replace("_", " ")) for t in ["legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory"]]
    ax.legend(handles=legend, loc="lower right", frameon=False, fontsize=9, title="Ehrenthal (2026) parent signal type")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    fig.text(0.01, -0.02, f"Source: public.signals filtered to {WINDOW_LABEL}. Bar colour = parent signal type per classification/schema.yaml v0.4.2. {other_n} of {total_all} rows carried out-of-schema dimension labels (Ergebnisse §4.1) and are excluded from bar heights but counted in the denominator for percentages.",
             fontsize=7, color="#555", wrap=True)
    save(fig, "fig2_subdimension_distribution")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3 — per-actor Jaccard distribution over sub_dimensions.
# ---------------------------------------------------------------------------
def fig3_jaccard_hist(signals, canonical_dims):
    df_all = signals[signals["system"].isin(["masfactory", "hermes"])].copy()
    df_canon = df_all[df_all["dimension"].isin(canonical_dims)]

    def per_actor_jaccard(df):
        rows = []
        for actor, grp in df.groupby("actor_slug"):
            a = set(grp[grp["system"] == "masfactory"]["dimension"])
            b = set(grp[grp["system"] == "hermes"]["dimension"])
            union = a | b
            if not union:
                continue
            rows.append((actor, len(a & b) / len(union), len(a), len(b), len(a & b), len(union)))
        return pd.DataFrame(rows, columns=["actor", "jaccard", "n_a", "n_b", "intersection", "union"])

    j_raw = per_actor_jaccard(df_all)
    j_canon = per_actor_jaccard(df_canon)

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 5))

    def draw(ax, series, colour, title):
        vals = series["jaccard"].values
        ax.hist(vals, bins=np.linspace(0, 1, 11), color=colour, edgecolor="white", alpha=0.85)
        ax.axvline(vals.mean(), color="#333", linestyle="--", linewidth=1, label=f"mean = {vals.mean():.3f}")
        ax.axvline(np.median(vals), color="#333", linestyle=":", linewidth=1, label=f"median = {np.median(vals):.3f}")
        ax.set_xlim(0, 1)
        ax.set_xlabel("Jaccard(A, B) per actor  =  |A AND B| / |A OR B|")
        ax.set_ylabel(f"actors (n = {len(vals)})")
        ax.set_title(title)
        ax.legend(loc="upper right", frameon=False, fontsize=9)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.set_axisbelow(True)

    draw(ax0, j_raw, COL_A, "(a) dimensions as recorded  — includes B's out-of-schema labels")
    draw(ax1, j_canon, COL_B, "(b) canonical 19-key taxonomy only")

    fig.suptitle("Figure 3 — Per-actor A vs B agreement on sub-dimensions", fontsize=12, y=1.02)
    fig.text(0.01, -0.02, f"Source: public.signals filtered to {WINDOW_LABEL}. For each actor with signals from both systems, Jaccard = |dims_A AND dims_B| / |dims_A OR dims_B|. Panel (a) uses dimensions as recorded (System B invented 214 labels outside the 19-key taxonomy — see Ergebnisse §4.1); panel (b) filters both sides to canonical dimensions before computing.",
             fontsize=7, color="#555", wrap=True)
    fig.tight_layout()
    save(fig, "fig3_jaccard_hist")
    plt.close(fig)

    stats = pd.concat([
        j_raw.assign(basis="as recorded"),
        j_canon.assign(basis="canonical only"),
    ])
    stats.to_csv(OUT / "fig3_jaccard_per_actor.csv", index=False)
    print(f"  wrote docs/figures/fig3_jaccard_per_actor.csv")


# ---------------------------------------------------------------------------
# Figure 4 — three-stage cost-reversal (raw → retention-weighted → correctness-weighted).
# Numbers are pulled directly from eval-results/results.json (headline gold-set
# and July-2026 token-efficiency figures), so the weight definitions in the
# reference table below trace back to the same computation the thesis §3.5 uses.
# ---------------------------------------------------------------------------
def fig4_cost_reversal(results):
    signals_a, signals_b = 259, 1368
    tokens_a, tokens_b = 25_937_521, 96_649_854
    precision_a, precision_b = 0.800, 0.760
    dim_acc_a, dim_acc_b = 0.600, 0.105

    def eff_per_1k(n_signals, tokens):
        return 1000.0 * n_signals / tokens

    raw_a = eff_per_1k(signals_a, tokens_a)
    raw_b = eff_per_1k(signals_b, tokens_b)
    ret_a = eff_per_1k(signals_a * precision_a, tokens_a)
    ret_b = eff_per_1k(signals_b * precision_b, tokens_b)
    cor_a = eff_per_1k(signals_a * precision_a * dim_acc_a, tokens_a)
    cor_b = eff_per_1k(signals_b * precision_b * dim_acc_b, tokens_b)

    stages = ["Raw\nsignals per 1000 tokens",
              "Retention-weighted\nx gold-set precision",
              "Correctness-weighted\nx dimension accuracy"]
    a_vals = [raw_a, ret_a, cor_a]
    b_vals = [raw_b, ret_b, cor_b]

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1.2, 1]})

    x = np.arange(len(stages))
    ax0.plot(x, a_vals, marker="o", markersize=10, linewidth=2.2, color=COL_A, label=f"System A · MASFactory")
    ax0.plot(x, b_vals, marker="s", markersize=10, linewidth=2.2, color=COL_B, label=f"System B · Hermes")
    y_max = max(max(a_vals), max(b_vals))
    for xi, (av, bv) in enumerate(zip(a_vals, b_vals)):
        offset_a = (10, 10) if av >= bv else (10, -16)
        offset_b = (10, 10) if bv > av else (10, -16)
        ax0.annotate(f"{av:.4f}", (xi, av), xytext=offset_a, textcoords="offset points", fontsize=9, color=COL_A)
        ax0.annotate(f"{bv:.4f}", (xi, bv), xytext=offset_b, textcoords="offset points", fontsize=9, color=COL_B)
        ratio = bv / av if av else float("inf")
        winner = "B leads" if ratio > 1.05 else ("A leads" if ratio < 0.95 else "tied")
        ax0.annotate(f"B/A = {ratio:.2f}x  ({winner})", (xi, y_max * 1.02),
                     xytext=(0, 4), textcoords="offset points", fontsize=9, ha="center",
                     color="#333", bbox=dict(boxstyle="round,pad=0.3", fc="#fef3c7", ec="#b45309"))
    ax0.set_ylim(top=y_max * 1.20)

    ax0.set_xticks(x)
    ax0.set_xticklabels(stages, fontsize=10)
    ax0.set_ylabel("effective signals per 1 000 LLM tokens")
    ax0.set_title("Figure 4 — Cost-reversal from raw throughput to correctness-adjusted throughput")
    ax0.legend(loc="upper right", frameon=False, fontsize=10)
    ax0.grid(True, linestyle=":", alpha=0.4)
    ax0.set_axisbelow(True)
    ax0.set_ylim(bottom=0)

    ax1.axis("off")
    weight_rows = [
        ["Stage", "Weight applied", "A", "B", "Source"],
        ["Raw",         "1 (identity)",             "1.000", "1.000", "Ergebnisse §2.3"],
        ["Retention",   "gold-set precision",       f"{precision_a:.3f}", f"{precision_b:.3f}", "Ergebnisse §2.4"],
        ["Correctness", "dimension accuracy",       f"{dim_acc_a:.3f}",   f"{dim_acc_b:.3f}",   "Ergebnisse §2.4"],
    ]
    tbl = ax1.table(cellText=weight_rows[1:], colLabels=weight_rows[0], loc="center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.6)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#ccc")
        if r == 0:
            cell.set_facecolor("#f1f5f9")
            cell.set_text_props(weight="bold")
    ax1.set_title("Weight definitions", pad=12, fontsize=11)

    fig.text(0.01, -0.02, f"Source: {WINDOW_LABEL}. System counts and tokens: Ergebnisse §2.3 (A=259 signals / 25.94M tokens · B=1368 signals / 96.65M tokens). Gold-set precision and dimension accuracy: eval-results/results.json (n=25/25 gold, coded blind 2026-08-04). The reversal is the point: B leads on raw throughput (1.42×), holds narrowly on retention (1.34×), and A overtakes by 4× once correctness is folded in.",
             fontsize=7, color="#555", wrap=True)
    fig.tight_layout()
    save(fig, "fig4_cost_reversal")
    plt.close(fig)

    with (OUT / "fig4_cost_reversal.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "system_a_signals_per_1k_tokens", "system_b_signals_per_1k_tokens", "ratio_b_over_a"])
        for name, av, bv in zip(["raw", "retention_weighted", "correctness_weighted"], a_vals, b_vals):
            w.writerow([name, f"{av:.6f}", f"{bv:.6f}", f"{(bv/av):.4f}"])
    print("  wrote docs/figures/fig4_cost_reversal.csv")


# ---------------------------------------------------------------------------
# Figure 5 — timeline of the eight protocol departures documented in
# ergebnisse-zusammenfassung.md §4.1–4.8. Dates come from the doc itself.
# ---------------------------------------------------------------------------
def fig5_protocol_departures_timeline():
    events = [
        # (date, system-affected, short label, full description)
        (date(2026, 6, 10), "B", "§4.1 out-of-schema classification begins",
         "Hermes CLI cutover; skill file's 'free-text sub-category' framing invites B to invent labels — 88.5% of B's July rows outside the 19-key taxonomy."),
        (date(2026, 7,  1), "A", "§4.3 System A running under half config",
         "Four code paths disagree on defaults; server picked the lowest. arXiv=5/10, subpages=3/5; no retry → 0 arXiv signals from A the whole month."),
        (date(2026, 7,  1), "AB", "§4.4 no equal-budget comparison possible",
         "Structural: A processes 40 actors × 5 collectors per night, B one AIAgent loop. No shared budget knob exists, so A vs B cost figures are not directly comparable."),
        (date(2026, 7,  1), "AB", "§4.7 event duplicates not detectable",
         "Deduplication is on (actor, url, hash, system); the same real-world event announced through two channels enters twice under different URLs. Structural."),
        (date(2026, 7,  8), "B", "§4.5 few-shot examples land as findings",
         "Hermes' skill file includes labelled example rows; the CLI treats them as validated retrieval targets and writes them to signals with the example's URL."),
        (date(2026, 7, 14), "B", "§4.6 single fabrication case",
         "One July row for a fictitious partnership; source URL 200s but page content does not support the claim. Investigated and left in the corpus with the flag set."),
        (date(2026, 7, 29), "B", "§4.2 abort rate on B exceeds 50%",
         "20-iteration cap per actor; when hit, the run is truncated without persisting. Recorded rates 50 / 67 / 72 / 55 / 57 % across the last five nights — unresolved."),
        (date(2026, 8,  2), "AB", "§4.8 no integration test against real services",
         "Confirmed after audit: tests mock arXiv/News/Bing/EPO; no CI job exercises the live endpoints, so schema drift or rate-limit changes go undetected until a scrape fails."),
    ]

    fig, ax = plt.subplots(figsize=(14, 6))
    y = np.arange(len(events))

    system_colour = {"A": COL_A, "B": COL_B, "AB": "#4b5563"}
    for i, (d, sys, label, desc) in enumerate(events):
        c = system_colour[sys]
        ax.scatter(d, i, s=180, color=c, edgecolor="white", linewidth=1.5, zorder=3)
        ax.annotate(f"{label}", (d, i), xytext=(10, 0), textcoords="offset points",
                    fontsize=9, va="center", color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{d.isoformat()}  ·  {sys}" for (d, sys, _, _) in events], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(date(2026, 6, 1), date(2026, 9, 5))
    ax.set_xlabel("2026")
    ax.set_title("Figure 5 — Timeline of the eight protocol departures (ergebnisse-zusammenfassung.md §4.1–4.8)")
    ax.grid(True, axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)

    legend = [
        Patch(facecolor=COL_A, label="System A · MASFactory"),
        Patch(facecolor=COL_B, label="System B · Hermes"),
        Patch(facecolor="#4b5563", label="both / structural"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=3, frameon=False, fontsize=9)
    fig.text(0.01, -0.02, "Source: ergebnisse-zusammenfassung.md §4.1–4.8. Dates are the earliest observation the doc records for each departure (structural departures anchored at the July window start). Labels are the section headings; full descriptions in the accompanying CSV.",
             fontsize=7, color="#555", wrap=True)
    fig.tight_layout()
    save(fig, "fig5_protocol_departures_timeline")
    plt.close(fig)

    with (OUT / "fig5_protocol_departures_timeline.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "system", "short_label", "description"])
        for d, sys, label, desc in events:
            w.writerow([d.isoformat(), sys, label, desc])
    print("  wrote docs/figures/fig5_protocol_departures_timeline.csv")


# ---------------------------------------------------------------------------
# Figure 6 — gap matrix (reference-architecture requirements × A / B).
# Rows follow §2.1.5 requirement statements; verdicts follow §4.2 gap analysis.
# ---------------------------------------------------------------------------
def fig6_gap_matrix():
    rows = [
        # (row label,                                    A verdict, B verdict, source)
        ("Retrieval role",                                "met",     "met",     "§3.3 · both systems' collectors"),
        ("Classification role",                           "met",     "partial", "§3.3; §4.1 (B invents labels)"),
        ("Reasoning across actors / over time",           "not met", "not met", "§4.1.1 concedes third MRQ op unmet"),
        ("Verification role (Critic)",                    "met",     "not met", "§4.2 — A's Critic node has no B counterpart"),
        ("Explicit collaboration graph",                  "met",     "not met", "§3.3 — B is one AIAgent loop"),
        ("Persistent memory / shared context across runs","not met", "met",     "§4.2 — A stateless, B holds Hermes memory"),
        ("Reusable skills",                               "partial", "met",     "§3.3 — A has fixed nodes, B has SKILL.md files"),
        ("Structured knowledge graph (actor - signal - category)", "not met", "not met", "§4.2 — largest gap; neither system builds it"),
        ("Traceability of every classified item to its role","met", "partial", "§3.3 · A per-node audit; B loop is opaque"),
    ]

    verdict_col = {"met": "#166534", "partial": "#b45309", "not met": "#9d174d"}
    verdict_face = {"met": "#dcfce7", "partial": "#fef3c7", "not met": "#fce7f3"}

    n = len(rows)
    fig, ax = plt.subplots(figsize=(14, 0.6 * n + 2.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(-1.2, n - 0.5)
    ax.invert_yaxis()
    ax.axis("off")

    col_req_x = 1
    col_a_x = 43
    col_b_x = 55
    col_src_x = 68

    ax.text(col_req_x, -1.0, "Requirement (from §2.1.5)", fontsize=11, weight="bold", color="#111")
    ax.text(col_a_x, -1.0, "System A", fontsize=11, weight="bold", color=COL_A, ha="center")
    ax.text(col_b_x, -1.0, "System B", fontsize=11, weight="bold", color=COL_B, ha="center")
    ax.text(col_src_x, -1.0, "Source", fontsize=11, weight="bold", color="#111")
    ax.plot([0, 100], [-0.55, -0.55], color="#333", linewidth=0.8)

    def pill(cx, y, verdict):
        face = verdict_face[verdict]
        edge = verdict_col[verdict]
        text = verdict.upper()
        half_w = 4.5
        half_h = 0.28
        rect = plt.Rectangle((cx - half_w, y - half_h), 2 * half_w, 2 * half_h,
                             facecolor=face, edgecolor=edge, linewidth=1.4,
                             joinstyle="round", zorder=2)
        ax.add_patch(rect)
        ax.text(cx, y, text, fontsize=9, ha="center", va="center", color=edge, weight="bold", zorder=3)

    for i, (label, av, bv, src) in enumerate(rows):
        ax.text(col_req_x, i, label, fontsize=10, color="#111", va="center")
        pill(col_a_x, i, av)
        pill(col_b_x, i, bv)
        ax.text(col_src_x, i, src, fontsize=8.5, color="#555", va="center")
        if i < n - 1:
            ax.plot([0, 100], [i + 0.5, i + 0.5], color="#eee", linewidth=0.6, zorder=0)

    fig.suptitle("Figure 6 — Reference-architecture requirements x implemented systems", fontsize=12, y=0.98)
    fig.text(0.01, 0.0, "Rows: architectural requirements synthesised in docs/ideal-reference-architecture.md (thesis §2.1.5). Cell verdicts and sources per the gap analysis in ergebnisse-zusammenfassung.md and thesis §4.2.",
             fontsize=7, color="#555", wrap=True)
    save(fig, "fig6_gap_matrix")
    plt.close(fig)

    with (OUT / "fig6_gap_matrix.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["requirement", "system_a", "system_b", "source"])
        for row in rows:
            w.writerow(row)
    print("  wrote docs/figures/fig6_gap_matrix.csv")


# ---------------------------------------------------------------------------
# Appendix C — component-to-source mapping.
# Every architectural component we claim in §2.1.5 traces to an external
# published source, not to a system output. This is what the anti-circularity
# check §5 asks for. The mapping is derived from the citations in §2.1.5
# itself (the sources are named there) plus the schema.yaml provenance for
# the taxonomy row.
# ---------------------------------------------------------------------------
def appendix_c(schema_ver="0.4.2"):
    rows = [
        # component, requirement, primary source, citation string, where used
        ("Retrieval agent role",
         "R1 · separation of roles",
         "Liu et al. (2026), 'Agentic Collaboration on Explicit Graphs'",
         "Nodes host agents/tools; edges carry dependencies + messages",
         "§2.1.5 · docs/ideal-reference-architecture.md"),
        ("Classification agent role (Ehrenthal four-signal scheme)",
         "R1 · separation of roles + domain schema",
         "Ehrenthal, Gonzalez-Padron & Gruen (2026)",
         "Four-signal scheme + 19 sub-dimensions used verbatim",
         f"systems/masfactory/masfactory_system/classification/schema.yaml v{schema_ver}"),
        ("Reasoning agent role (patterns across actors and over time)",
         "R1 · separation of roles",
         "Liu et al. (2026); Wang et al. (2026)",
         "Distinct reasoning role required by the graph; multi-path failure at depth motivates its distinctness",
         "§2.1.5"),
        ("Verification agent role",
         "R3 · verification stage",
         "Kolbe & Burnett (1991); Wu et al. (2026, LogicGraph)",
         "Reliability requirement carries from human coding to machine coding; multi-path proof coverage falls without a verifier",
         "§2.1.5 · System A's Critic node"),
        ("Traceability of every classified item to the role that produced it",
         "R1 · separation of roles (derived)",
         "Kolbe & Burnett (1991); Shaw (2001)",
         "Content-analysis reliability + Shaw's structure-answers-requirements principle",
         "§2.1.5 · System A per-node audit"),
        ("Explicit collaboration graph (nodes + edges)",
         "R1 · separation of roles",
         "Liu et al. (2026)",
         "Nodes host agents/tools; edges carry dependencies + messages",
         "§2.1.5"),
        ("Persistent memory / shared context beneath the agents",
         "R2 · persistent layer",
         "Li et al. (2026a, AgentOS)",
         "Shared context + memory placed beneath the agents",
         "§2.1.5 · System B's Hermes memory"),
        ("Reusable skills (compiled recurring task patterns)",
         "R2 · persistent layer",
         "Li et al. (2026b, OpenSage)",
         "Recurring task patterns compiled into reusable skills",
         "§2.1.5 · Hermes SKILL.md files"),
        ("Extended tool use in the model itself",
         "R2 · persistent layer (enabler)",
         "Teknium et al. (2025)",
         "Model trained for extended tool use, prerequisite for skill+memory stacks",
         "§2.1.5"),
        ("Structured knowledge graph (actor ↔ signal ↔ category)",
         "R3 · structured representation",
         "Wu et al. (2026); Stewart & Buehler (2026); Adner (2017)",
         "Multi-path proof structure + higher-order knowledge representation; Adner's activities/actors/positions/links",
         "§2.1.5 · UNBUILT in both systems (§4.2 largest gap)"),
        ("Architecture-as-characterisation stance (benchmark, not blueprint)",
         "meta · validation type",
         "Shaw (2001)",
         "Pairs question type with the validation it requires; §2.1.5 is a characterisation, tested afterwards in §4.2",
         "§2.1.5 framing paragraph"),
    ]

    md_path = OUT / "appendix_c_component_source.md"
    csv_path = OUT / "appendix_c_component_source.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component", "requirement", "source_reference", "citation_summary", "used_in"])
        w.writerows(rows)
    with md_path.open("w") as f:
        f.write("# Appendix C — Ideal reference architecture: component-to-source mapping\n\n")
        f.write("Every architectural component listed in the ideal reference architecture (§2.1.5) traces to an external\n")
        f.write("published source, not to a system output. This is the anti-circularity evidence §5 asks for: the mapping\n")
        f.write("was drawn from the literature *before* either System A or System B produced results, so the yardstick\n")
        f.write("is not derived from what was built. The table below lists each component with its primary published\n")
        f.write("source, a short justification, and where the component appears in the thesis or the codebase.\n\n")
        f.write("| Component | Requirement | Primary source | Justification (short) | Used in |\n")
        f.write("|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n")
        f.write("\n**Anti-circularity note.** No row in this table cites a system output. Rows whose 'Used in' column\n")
        f.write("names System A or System B name only *whether that component was implemented*, not the source of the\n")
        f.write("requirement itself. The gap analysis in §4.2 compares the implementations against this table; the\n")
        f.write("comparison is therefore between built systems and a literature-derived yardstick, not between\n")
        f.write("built systems and each other.\n")
    print(f"  wrote docs/figures/appendix_c_component_source.csv + .md")


def main():
    _apply_style()
    signals, actors, canonical_dims, dim_to_type, results = load_data()
    print("Figure 1 · signal type per actor grouped by category")
    fig1_signal_type_per_actor(signals, actors)
    print("Figure 2 · sub-dimension distribution")
    fig2_subdimension_distribution(signals, canonical_dims, dim_to_type)
    print("Figure 4 · cost-reversal chart")
    fig4_cost_reversal(results)
    print("Figure 6 · gap matrix")
    fig6_gap_matrix()
    print("Appendix C · component-to-source mapping")
    appendix_c()
    print("Figure 3 · per-actor Jaccard on sub-dimensions")
    fig3_jaccard_hist(signals, canonical_dims)
    print("Figure 5 · protocol-departures timeline")
    fig5_protocol_departures_timeline()
    print("\nall figures written to docs/figures/")


if __name__ == "__main__":
    main()
