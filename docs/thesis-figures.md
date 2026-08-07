# Thesis figures — captions, provenance, reproduction

Six figures + one appendix, all restricted to the retrieval window
**2026-07-01 ≤ inserted_at < 2026-08-01** (July 2026 — the one clean, complete
month per `ergebnisse-zusammenfassung.md §5`). Every plot and table lives in
`docs/figures/` as PNG (200 dpi) + SVG + the underlying CSV. All are regenerated
from a single command:

```bash
python scripts/figures/pull_july_2026.py    # once, needs SUPABASE_DB_URL
python scripts/figures/make_figures.py      # regenerates everything into docs/figures/
```

`pull_july_2026.py` reads `SUPABASE_DB_URL` from env; the pulled CSVs
(`data/july_2026_*.csv`) are the frozen inputs — the plotting script never
touches Supabase again, so the figures are reproducible on any laptop with the
CSVs checked in.

## Overview

| # | File (PNG / SVG / CSV) | Thesis section | What it shows |
|---|---|---|---|
| 1 | `docs/figures/fig1_signal_type_per_actor.*` | 3.5 · SRQ1 | Signal-type distribution across 40 actors, grouped by Swissnex reporting category. Stacked horizontal bar. |
| 2 | `docs/figures/fig2_subdimension_distribution.*` | 3.5 · SRQ1 | Sub-dimension distribution across the 19-key canonical taxonomy, coloured by parent signal type. |
| 3 | `docs/figures/fig3_jaccard_hist.*` | 3.5 · SRQ3 reliability | Per-actor Jaccard between System A and System B on sub-dimensions. Two panels: as recorded, and canonical-only. |
| 4 | `docs/figures/fig4_cost_reversal.*` | 3.5 · SRQ3 headline | Cost-reversal from raw throughput → retention-weighted → correctness-weighted signals per 1000 tokens. B leads 1.42×; A leads 4× once correctness is folded in. |
| 5 | `docs/figures/fig5_protocol_departures_timeline.*` | 4.1 critical appraisal | Timeline of the eight protocol departures (`ergebnisse-zusammenfassung §4.1–4.8`). |
| 6 | `docs/figures/fig6_gap_matrix.*` | 4.2 gap analysis | Requirements from §2.1.5 × implemented systems (met / partial / not met). |
| C | `docs/figures/appendix_c_component_source.*` | Appendix C · anti-circularity | Component-to-source mapping — every architectural block in §2.1.5 traces to an external published source, not a system output. |

## Full captions (paste into the docx under each figure)

### Figure 1 — Signal-type distribution across 40 actors, grouped by Swissnex reporting category (July 2026)

Source: `public.signals` filtered to 2026-07-01 ≤ inserted_at < 2026-08-01
(n=1627). Signals from System A (MASFactory, 259) and System B (Hermes, 1368)
are pooled per actor. Each bar is one actor, sorted within Swissnex reporting
category by total signal count. Stack colours code the Ehrenthal (2026)
four-signal scheme; the grey "other/out-of-schema" slice captures the 88.5 % of
System B rows whose classifier invented a `signal_type` value outside the
canonical taxonomy (see `ergebnisse-zusammenfassung.md §4.1`). Answers SRQ1
directly: universities and research hubs are legitimacy-heavy, private companies
lean on customer co-creation and future-trajectory, ecosystem builders on
community-ecosystem.

### Figure 2 — Sub-dimension distribution across the 19-key canonical taxonomy (July 2026)

Source: `public.signals` filtered to July 2026 (n=1627). Bar length = signals in
each canonical dimension; bar colour = parent signal type per
`systems/masfactory/masfactory_system/classification/schema.yaml` v0.4.2. 1198
of 1627 rows carried out-of-schema labels (Ergebnisse §4.1) — excluded from bar
heights but retained in the denominator for percentages. `patents = 0` because
System A's EPO collector was env-gated off for July and System B never called
the equivalent tool; this is a data availability finding, not a domain finding.

### Figure 3 — Per-actor A vs B agreement on sub-dimensions (July 2026)

Source: `public.signals` filtered to July 2026. For each actor with signals from
both systems, Jaccard = |dims_A AND dims_B| / |dims_A OR dims_B|. Panel (a) uses
dimensions as recorded (System B invented 214 labels outside the 19-key
taxonomy, floor of the distribution stays at 0). Panel (b) filters both sides
to canonical dimensions before computing (mean lifts to 0.099; three actors
reach ≥ 0.4). The gap between panels is the size of the classification-drift
problem: the systems agree meaningfully on *what to look at* only after the
taxonomy is enforced, which motivates the pre-registered v0.4.2 skill rewrite
of 2026-08-02.

### Figure 4 — Cost-reversal from raw throughput to correctness-adjusted throughput (July 2026)

Source: July 2026. System counts and tokens: Ergebnisse §2.3 (A = 259 signals /
25.94M tokens; B = 1368 signals / 96.65M tokens). Retention weight = gold-set
precision, correctness weight = dimension accuracy vs gold; both from
`eval-results/results.json` (n = 25/25 gold rows, blind coded 2026-08-04).

The three stages compose multiplicatively:

- **Raw:** `signals / (tokens / 1000)`. B leads 1.42×.
- **Retention-weighted:** raw × (fraction of signals the human coder marked
  worth keeping). B still leads 1.35×.
- **Correctness-weighted:** retention × (fraction of retained signals correctly
  labelled at the 19-key dimension level). A leads 4×.

The reversal is the empirical centrepiece answering SRQ3. It makes explicit
what raw throughput hides: a token-efficient system that produces
correctly-classified findings costs less per unit of usable output than a
token-*apparently*-efficient system that produces mostly mis-labelled ones.
Weight definitions are reproduced in the plot's right-hand table so any reader
can substitute their own coefficients.

### Figure 5 — Timeline of the eight protocol departures (July 2026)

Source: `docs/ergebnisse-zusammenfassung.md §4.1–4.8`. Dates are the earliest
observation each section records; structural departures (§4.4, §4.7) are
anchored to the July window start. Colour codes the affected system.
Read together with the pre-registration in `docs/pre-registration.md`, this is
the honest record of what deviated from the protocol and why — the material for
the "Limitations" chapter, not for hiding.

### Figure 6 — Reference-architecture requirements × implemented systems (July 2026)

Rows are the requirements synthesised in `docs/ideal-reference-architecture.md`
(thesis §2.1.5). Cell verdicts and their sources come from the gap analysis in
`ergebnisse-zusammenfassung.md` and thesis §4.2. The one row that neither
system met — a structured knowledge graph over (actor, signal, category) — is
the largest gap and the reason SRQ4 answers "reasoning across actors and over
time" negatively even where retrieval and classification succeed.

### Appendix C — Ideal reference architecture: component-to-source mapping

The full markdown table lives at
[`docs/figures/appendix_c_component_source.md`](figures/appendix_c_component_source.md)
(machine-readable CSV alongside it). Every component listed in §2.1.5 is
traced to an external published source (Liu et al. 2026, Li et al. 2026a/b,
Teknium et al. 2025, Wu et al. 2026, Wang et al. 2026, Stewart & Buehler 2026,
Kolbe & Burnett 1991, Shaw 2001, Ehrenthal et al. 2026). No row cites a system
output — this is the anti-circularity evidence the discussion in §5 asks for.

## Missing right now

Nothing blocking. The raw CSVs (`data/july_2026_*.csv`) are pulled and
committed, so re-running `make_figures.py` after a schema tweak takes seconds
and needs no DB access.
