"""Methodology — full transparency on how the dashboard's scores are computed.

This is the page Anna will point her supervisor to when defending the
quantitative claims on the other pages.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard_app import labels as L


st.set_page_config(page_title="Methodology", layout="wide", page_icon="📐")
st.title("📐 Methodology")
st.caption(
    "How every number on this dashboard is computed, where the data comes from, and which "
    "academic frame justifies each design choice. Bachelor Thesis — Anna Geiser, FHNW."
)

st.markdown(
    """
### The big picture

Deep-tech markets like quantum computing don't yet have the price / share /
benchmark data that classical market research relies on. The thesis builds
two AI systems that read public **signals** instead — papers, patents,
partnerships, hires, announcements — and turns the volume + mix + recency of
those signals into a comparable picture of who's doing what.

The dashboard sits on top of the signal database both systems write to. It
never invents data; every number is a transparent transformation of the
underlying rows.
"""
)

st.markdown("---")

st.markdown("### The 9 signal dimensions")
st.caption(
    "Each signal is classified into exactly one dimension. The taxonomy is grounded in "
    "signalling-theory and high-technology marketing literature (Suchman 1995; Knight & Cavusgil 2004; "
    "Mohr & Sarin 2009; Ehrenthal et al. 2026). Edit "
    "`systems/masfactory/masfactory_system/classification/schema.yaml` to evolve it."
)

dim_df = pd.DataFrame(
    [
        {
            "Dimension": L.dimension(k),
            "Lens": "Capability" if k in L.CAPABILITY_DIMENSIONS else "Legitimacy",
            "What it covers": L.DIMENSION_HINT[k],
            "Weight in Impact": L.DIMENSION_WEIGHT[k],
        }
        for k in L.DIMENSION_LABEL.keys()
    ]
)
st.dataframe(dim_df, use_container_width=True, hide_index=True)

st.markdown(
    """
**Capability vs. legitimacy.** Following Suchman (1995) and Knight & Cavusgil (2004),
we separate signals that demonstrate *what an actor can technically do*
(papers, patents, infrastructure) from signals that demonstrate
*social acceptance / strategic positioning* (partnerships, funding, hires,
positioning). Most healthy actors balance the two; the **Authority** score
on the leaderboard tracks the ratio.
"""
)

st.markdown("---")

st.markdown("### The four scores")
st.markdown(
    """
| Score | Formula | What it answers |
|---|---|---|
| **Impact** | `Σ_i ( dimension_weight_i × confidence_i )` | "How much should an outside observer update their view of this actor based on what they've publicly said in this window?" |
| **Momentum** | `signals_last_7d − signals_prev_7d` | "Are they accelerating or cooling?" |
| **Diversity** | `count(distinct dimensions)` | "Are they signalling across multiple fronts, or doing the same thing repeatedly?" |
| **Authority** | `(capability_signals + 1) / (capability + legitimacy + 2)` | "Is their signalling more about *what they can build* or about *who they're with*?" |

The Authority formula uses Laplace smoothing (+1 / +2) so a single-signal actor doesn't get scored 0.0 or 1.0 deterministically.

**Confidence** for each signal is set by the Classifier agent during scraping; it reflects how sure the model is that the signal genuinely belongs to the assigned dimension (and actor).
"""
)

st.markdown("---")

st.markdown("### Where the data comes from")
st.markdown(
    """
| Source | What's collected | How often |
|---|---|---|
| **arXiv** (`export.arxiv.org/api/query`) | Recent pre-prints whose abstract / affiliation matches an actor's `arxiv_query` | Each system, once a day |
| **Actor websites** | One-page fetch of the homepage, visible-text extracted | Each system, once a day |
| **Swissreg patents** | (reserved — collector stub in place; not yet wired) | TODO |

Both AI systems hit the same sources but use different reasoning pipelines:

- **System A — MASFactory** orchestrates 7 specialised agents in a directed graph (Planner → Retriever → Extractor → Classifier → Critic → Analyst → Persistence).
- **System B — Hermes** is a single long-running agent loop with skills + procedural memory, modelled after Nous Research's Hermes Agent design.

Comparing the two on the same task is the empirical core of the thesis. The dashboard's *Data source* filter (sidebar) lets you isolate one or look at both.
"""
)

st.markdown("---")

st.markdown("### Reading the dashboard responsibly")
st.markdown(
    """
- **Absence of signal ≠ absence of activity.** An actor with zero signals this week may simply not have published anything publicly. The system reads only what's machine-readable from the listed sources.
- **Confidence matters.** A high-confidence funding signal is more meaningful than a low-confidence positioning signal. The Confidence column is shown everywhere it's available.
- **Cross-system check.** When both systems collect the same actor and disagree dramatically on signal count, that's a flag — see the cross-system table on Home.
- **Audit trail.** Every signal traces back to a verbatim quote and a source URL. Every system run gets a folder under `data/raw/runs/<CET-iso>__<system>/` on the VPS, kept indefinitely. Reproducibility is the thesis's primary non-functional requirement.
"""
)

st.markdown("---")

st.markdown(
    """
### References

- Ehrenthal, J., Gonzalez-Padron, T., & Gruen, T. W. (2026). *Global Strategic Marketing When Performance Is Noncommensurable: How Quantum-Computing Vendors Articulate Global Positions Through Nontechnical Signals.*
- Knight, G. A., & Cavusgil, S. T. (2004). *Innovation, Organizational Capabilities, and the Born-Global Firm.* JIBS 35(2), 124–141.
- Liu, Y. et al. (2026). *MASFactory: A Graph-centric Framework for Orchestrating LLM-Based Multi-Agent Systems with Vibe Graphing.* arXiv:2603.06007.
- Mohr, J. J., & Sarin, S. (2009). *Drucker's Insights on Market Orientation and Innovation: Implications for Emerging Areas in High-Technology Marketing.* JAMS 37(1), 85–96.
- Nous Research (2025). *Hermes Agent.* MIT License.
- Suchman, M. C. (1995). *Managing Legitimacy: Strategic and Institutional Approaches.* AMR 20(3), 571–610.

Code, prompts, and the full disposition are on [GitHub](https://github.com/annageiser/mas-deeptech-research).
"""
)
