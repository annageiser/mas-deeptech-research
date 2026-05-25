"""Methodology — full transparency on how the dashboard's scores are computed.

Ehrenthal-centric framing per the thesis's central proposition.
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
### The core thesis proposition

> *In deep-tech markets like quantum computing, the classical anchors of
> market research — prices, market shares, benchmarks, customer reviews —
> do not exist or are too noisy to be comparable across vendors. What
> remains are **observable public signals**: papers, patents, partnerships,
> hires, funding announcements, positioning statements. Aggregating these
> signals at scale gives a tractable substitute for the missing
> comparability.*

The thesis operationalises this proposition in code. Both AI systems harvest
the same signals from the same public sources daily; the dashboard renders
the result; the comparison between the two systems is itself the empirical
contribution.

The proposition is built on:
- **Ehrenthal, Gonzalez-Padron & Gruen (2026)** — "Global Strategic
  Marketing When Performance Is Noncommensurable: How Quantum-Computing
  Vendors Articulate Global Positions Through Nontechnical Signals". *The*
  core reference for the project. The signal taxonomy here is a direct
  operationalisation of their two-channel framing.
- **Hilkamo & Granqvist (2022)** — *De novo* market categories like quantum
  computing get their meaning through analogies, metaphors, and narrative
  legitimation, not initial product comparison.
- **Adner (2017)** — Ecosystem-as-structure: the right unit of analysis for
  emergent deep-tech markets is not "the firm" or "the industry" but the
  network of actors and the alignment dependencies between them.
- **Tomesh et al. (2022, SupermarQ)** — No unified quantum-computing
  benchmark exists, which is why we read signals as proxies in the first
  place.
"""
)

st.markdown("---")

st.markdown("### Two signal channels")
st.markdown(
    """
Following **Suchman (1995)** on strategic vs. cognitive legitimacy and
**Knight & Cavusgil (2004)** on capability-based competitive advantage, the
taxonomy divides every signal into one of two channels:

- **Capability evidence** — papers, patents, infrastructure, technical
  capability claims. Costly signals; they demonstrate *what the actor can
  technically do*.
- **Legitimacy evidence** — partnerships, funding, hires, policy presence,
  market positioning. Mostly cheaper signals; in *de novo* categories like
  quantum, they are how an actor publicly claims category membership
  (Hilkamo & Granqvist 2022; Robinson & Veresiu 2025 on legitimacy timing;
  Song, Zhao & Wei 2025 on coattail legitimacy effects).

The dashboard's **Authority** score is the ratio between the two — see below.
"""
)

st.markdown("---")

st.markdown("### The 9 signal dimensions")
st.caption(
    "Edit `systems/masfactory/masfactory_system/classification/schema.yaml` to evolve the "
    "taxonomy — it carries the canonical weights and the literature grounding for each "
    "dimension."
)
dim_df = pd.DataFrame(
    [
        {
            "Dimension": L.dimension(k),
            "Channel": "Capability" if k in L.CAPABILITY_DIMENSIONS else "Legitimacy",
            "Definition": L.DIMENSION_HINT[k],
            "Weight": L.DIMENSION_WEIGHT[k],
        }
        for k in L.DIMENSION_LABEL.keys()
    ]
)
st.dataframe(dim_df, use_container_width=True, hide_index=True)

st.markdown(
    """
**Why these weights?** Capability evidence is *costlier to fake* than
legitimacy evidence (Suchman 1995), so it carries higher weight per signal
— but only modestly so, because the empirical question of the thesis is
whether nontechnical signals are sufficient on their own (Ehrenthal et al.'s
core question). Funding is the highest-weight signal because it's the
costliest single-event signal (Rieger et al. 2025 link IP and trademark
filings to seed-funding outcomes). Market positioning carries the lowest
weight because it's the cheapest signal a vendor can emit.
"""
)

st.markdown("---")

st.markdown("### The four actor scores")
st.markdown(
    """
| Score | Formula | What it answers |
|---|---|---|
| **Impact** | `Σ_i ( weight_i × confidence_i )` | "How much should an outside observer update their view of this actor based on what they've publicly said in this window?" |
| **Momentum** | `signals_last_7d − signals_prev_7d` | "Are they accelerating or cooling?" |
| **Diversity** | `count(distinct dimensions)` | "Are they signalling across multiple fronts, or doing the same thing repeatedly?" |
| **Authority** | `(capability + 1) / (capability + legitimacy + 2)` | "Is their signalling more about *what they can build* or about *who they're with*?" |

**Authority** uses Laplace smoothing (+1 / +2) so a single-signal actor
doesn't get scored 0.0 or 1.0 deterministically.

**Confidence** for each signal is set by the Classifier agent during
scraping; it reflects how sure the model is that the signal genuinely
belongs to the assigned dimension AND the assigned actor (the second
constraint is enforced server-side after the classification — see the
defensive validation in `agents/persistence.py`).
"""
)

st.markdown("---")

st.markdown("### Why two systems")
st.markdown(
    """
The thesis is fundamentally a *comparative* contribution. Two
architectures, same task, same sources, same OpenRouter key:

- **System A — MASFactory** (Liu et al. 2026): an orchestration-centric
  directed graph of 7 specialised agents (Planner → Retriever → Extractor
  → Classifier → Critic → Analyst → Persistence). Transparent, easy to
  audit per-node.
- **System B — Hermes** (after Nous Research 2025): a single long-running
  AIAgent loop with procedural memory in SQLite and skill files in the
  agentskills.io format. Lower transparency, but potentially adapts over
  time as recurring tasks become "skills".

The **System A vs System B** page shows their per-actor agreement and
disagreement. The interesting empirical question is not which one wins but
where and why they differ.
"""
)

st.markdown("---")

st.markdown("### Where the data comes from")
st.markdown(
    """
| Source | What's collected | Method | How often |
|---|---|---|---|
| **arXiv** (`export.arxiv.org/api/query`) | Recent pre-prints matching the actor's `arxiv_query` field | Atom API, ranked by submission date | Each system, once a day |
| **Actor websites** | Homepage + RSS/Atom feed entries + newsy subpages (up to 5 docs per actor) | httpx + selectolax + feedparser; robots.txt honoured; 1 req/sec/host; deterministic disk cache | Each system, once a day |
| **Swissreg patents** | (reserved — collector stub in place; not yet wired) | — | — |
| **Broader web** | (planned: Google News / press aggregator) | Justified under Kolbe & Burnett 1991 content-analysis methodology | — |

Each scrape produces one `Document` per page, with a content hash and
source URL. The Extractor reads those documents, surfaces signal candidates
with verbatim evidence quotes, and the Classifier labels them. The
Persistence step does a server-side check: signals whose
`(actor_slug, source_url)` doesn't appear in the input document list get
**dropped as hallucinations** — recorded to
`data/raw/runs/<ts>/dropped_hallucinations.json` for audit.
"""
)

st.markdown("---")

st.markdown("### Reading the dashboard responsibly")
st.markdown(
    """
- **Absence of signal ≠ absence of activity.** An actor with zero signals
  this week may simply not have published anything publicly. The system
  reads only what's machine-readable from the listed sources.
- **Confidence matters.** A high-confidence funding signal is more
  meaningful than a low-confidence positioning signal. The Confidence
  column is shown everywhere it's available.
- **Cross-system check.** When both systems collect the same actor and
  disagree dramatically on signal count, that's a flag — see the
  System A vs System B page.
- **Audit trail.** Every signal traces back to a verbatim quote and a
  source URL. Every system run gets a folder under
  `data/raw/runs/<CET-iso>__<system>/` on the VPS, kept indefinitely.
  Reproducibility is the thesis's primary non-functional requirement
  (Kasanen, Lukka & Siitonen 1993 on constructive research approach).
- **Recall vs. precision.** The scoring favours recall (better to surface
  a weak signal than miss a strong one), which is why the Critic agent is
  conservative about dropping. Adjust by raising `Min confidence` on the
  Signals raw-table page.
"""
)

st.markdown("---")

st.markdown(
    """
### References

**Primary frame**

- Ehrenthal, J., Gonzalez-Padron, T., & Gruen, T. W. (2026). *Global
  Strategic Marketing When Performance Is Noncommensurable: How
  Quantum-Computing Vendors Articulate Global Positions Through
  Nontechnical Signals.*

**Signal & legitimacy theory**

- Adner, R. (2017). Ecosystem as Structure: An Actionable Construct for
  Strategy. *Journal of Management*, 43(1), 39–58.
- Hilkamo, O., & Granqvist, N. (2022). Giving Sense to de novo Market
  Categories: Analogies and Metaphors in the Early Emergence of Quantum
  Computing. *Research in the Sociology of Organizations*, 80, 57–79.
- Knight, G. A., & Cavusgil, S. T. (2004). Innovation, Organizational
  Capabilities, and the Born-Global Firm. *Journal of International
  Business Studies*, 35(2), 124–141.
- Mohr, J. J., & Sarin, S. (2009). Drucker's Insights on Market Orientation
  and Innovation: Implications for Emerging Areas in High-Technology
  Marketing. *Journal of the Academy of Marketing Science*, 37(1), 85–96.
- Reid, S. E., & de Brentani, U. (2010). Market Vision and Market
  Visioning Competence: Impact on Early Performance for Radically New,
  High-Tech Products. *JPIM*, 27(4), 500–518.
- Rieger, V., Dreller, A., & Engelen, A. (2025). Zooming In on the Very
  Early Days: The Role of Trademark Applications in the Acquisition of
  Venture Capital Seed Funding. *JMR*, 62(1), 170–188.
- Robinson, T. D., & Veresiu, E. (2025). Timing Legitimacy: Identifying
  the Optimal Moment to Launch Technology in the Market. *Journal of
  Marketing*, 89(3), 136–153.
- Song, X., Zhao, L., & Wei, Z. (2025). Ride who's coattails? *Technology
  Analysis & Strategic Management*, 37(13), 4376–4390.
- Suchman, M. C. (1995). Managing Legitimacy: Strategic and Institutional
  Approaches. *Academy of Management Review*, 20(3), 571–610.
- Blomqvist, K., Hurmelinna-Laukkanen, P., Nummela, N., & Saarenketo, S.
  (2008). The role of trust and contracts in the internationalization of
  technology-intensive Born Globals. *JETM*, 25(1), 123–135.

**Quantum-domain context**

- Tomesh, T. et al. (2022). *SupermarQ: A Scalable Quantum Benchmark
  Suite.* arXiv:2202.11045.
- swissnex (2025). *Switzerland Hub Quantum — October 2025 web report.*
- Swiss Quantum Initiative (SQI). https://quantum.scnat.ch/en

**Multi-agent system frameworks**

- Liu, Y. et al. (2026). *MASFactory: A Graph-centric Framework for
  Orchestrating LLM-Based Multi-Agent Systems with Vibe Graphing.*
  arXiv:2603.06007.
- Nous Research (2025). *Hermes Agent.* MIT Licence.

**Methodology**

- Kasanen, E., Lukka, K., & Siitonen, A. (1993). The constructive
  approach in management accounting research. *Journal of Management
  Accounting Research*, 5, 243–264.
- Kolbe, R. H., & Burnett, M. S. (1991). Content-Analysis Research: An
  Examination of Applications with Directives for Improving Research
  Reliability and Objectivity. *Journal of Consumer Research*, 18(2),
  243–250.
- Shaw, M. (2001). The coming-of-age of software architecture research.
  *ICSE 2001*, 656–664.

Code, prompts, and the full disposition are on
[GitHub](https://github.com/annageiser/mas-deeptech-research).
"""
)
