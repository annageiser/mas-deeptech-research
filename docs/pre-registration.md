# Pre-registration — empirical evaluation protocol

**Locked-in protocol for the BSc thesis empirical chapter.** This document commits to *what* will be measured, *how*, and *what counts as success* — written before looking at the live evaluation numbers. Departures from this protocol after the data is in must be justified explicitly in Chapter 4.

**Project:** Multi-Agent Systems for Ecosystem Mapping Under Noncommensurable Performance
**Author:** Anna Geiser
**Supervisor:** Prof. Dr. Joachim Ehrenthal
**Locked at:** 2026-06-02 (commit `<this commit>`)
**Last revised:** 2026-06-02

---

## 1 — Hypotheses

| ID | Hypothesis | Direction | Falsification criterion |
|---|---|---|---|
| H1 | The two MAS architectures (System A orchestration-centric, System B memory-and-skill-centric) produce **different signal corpora on identical inputs**. | two-tailed | Per-actor source_url Jaccard ≥ 0.85 (macro) across the 4-week evaluation window would falsify the "different" claim. |
| H2 | System A is **more token-efficient** than System B on volume terms (signals persisted per 1 000 LLM tokens). | one-tailed (A > B) | Ratio_A/B ≤ 1.1 would falsify; ratio_A/B ≥ 1.5 would strongly support. |
| H3 | The two systems achieve **comparable classification quality** vs. a hand-labelled gold set on the 4-way `signal_type` task. | two-tailed | Absolute F1 gap ≥ 0.15 on the macro-F1 between systems would constitute a meaningful asymmetry. |
| H4 | Both systems' re-run Jaccard is **strictly below 1.0** and **strictly above 0.5** on a fixed actor cohort with identical config — i.e. the system is partially-reproducible, with the gap attributable to (a) LLM non-determinism and (b) source-list freshness. | two-tailed bracket | Re-run Jaccard ≥ 0.95 would invalidate the "world isn't reproducible" framing; ≤ 0.4 would indicate the systems are too noisy to be useful. |
| H5 | The optional capability layers (consensus Critic, debate Critic, semantic dedup, embeddings) **each produce a measurable marginal improvement** on at least one of the four headline metrics, vs the unmodified baseline. | one-tailed per layer | A layer that moves no metric by more than ±2% (vs baseline) on a matched-cohort A/B run is reported as "no measurable effect" — and the thesis discusses why an apparently-defensible literature pattern produced no measurable lift in this specific context. |

---

## 2 — Metrics, units, and decision rules

| Metric | Unit | Aggregation | Decision rule |
|---|---|---|---|
| **Inter-system agreement** | Jaccard ∈ [0, 1] over per-actor `source_url` sets | Macro mean across actors + union-weighted mean | Tested against H1's 0.85 falsification threshold. Reported with 95% bootstrap CI on the actor distribution. |
| **Token efficiency** | Signals persisted / 1 000 (input + output) tokens, per system | Per-run mean × system; report ratio A/B | Tested against H2's 1.1 ≤ ratio_A/B ≤ 1.5 brackets. |
| **Classification quality** (4-way `signal_type`) | Macro F1, accuracy, Cohen's κ vs gold set | Per-system + ecosystem-wide | Tested against H3's 0.15 gap threshold. |
| **Classification quality** (19-way `dimension`) | Macro F1, accuracy, Cohen's κ vs gold set | Same as above | Reported descriptively; the 4-way metric is the headline. |
| **Critic keep-decision quality** | Precision / recall / F1 of (`confidence ≥ 0.45`) vs gold `keep` | Per-system + ecosystem-wide | Reported descriptively. |
| **Reproducibility** | Jaccard ∈ [0, 1] over (actor_slug, source_url) tuples between two consecutive runs of the same (system, cohort, config). | Mean across matched pairs, per system | Tested against H4's 0.5–0.95 bracket. |

Bootstrap CI: 1 000 resamples of the actor list, percentile method. Reported for the two metrics where the actor sample is the unit of analysis (inter-system agreement and per-actor classification quality).

---

## 3 — Evaluation window

| Parameter | Value | Rationale |
|---|---|---|
| Evaluation window | **2026-06-09 → 2026-07-06 (28 days)** | One full month of dual-system cron output. Lock the calendar window at the start so late additions to the corpus don't shift the metrics. |
| Run frequency in window | Daily (existing cron) | 02:00 CET System A, 05:00 CET System B. |
| Frozen-for-defence snapshot | **2026-07-07 09:00 CET** | `python -m eval_app.runner all --window-days 28` runs once at this moment; the `data/eval/<UTC-iso>/` folder produced is the thesis-cited folder. No re-runs after this point. |
| Actor cohort | All 40 Swiss-quantum actors (`data/raw/actors.yaml` as of 2026-06-02) | Frozen at the start of the window to keep the cohort invariant. |
| Optional capability layers | OFF for the baseline 4-metric run | A/B runs for each layer happen on separate cohorts (see §4). |

---

## 4 — Optional capability layer A/B

Five env-gated layers (see [`docs/architecture.md`](architecture.md) §Optional capability layers) are evaluated **one-at-a-time** against the baseline.

| Layer | Env var | A/B protocol |
|---|---|---|
| Embeddings | `MASF_EMBEDDINGS=1` | 7-day comparison window starting 2026-06-09 with embeddings ON vs OFF on a fixed 10-actor sub-cohort. Recorded: persisted-signal count + token cost. |
| Semantic dedup | `MASF_SEMANTIC_DEDUP=1` | Requires embeddings ON. Same 7-day sub-cohort: count of signals dropped by dedup + ground-truth check on the dropped set (manual: were they actually duplicates?). |
| Consensus Critic | `MASF_CRITIC_CONSENSUS_PASSES=3` | Same 7-day sub-cohort: persisted-signal count + token cost + Critic-pass disagreement rate from the `critic_consensus_audit` blob. |
| Debate Critic | `MASF_CRITIC_DEBATE_ROUNDS=1` | Same 7-day sub-cohort: vs consensus-only and vs baseline. |
| EPO OPS patents | `EPO_OPS_CONSUMER_KEY/SECRET` | Whole 28-day window since patents are a separate `source_kind` — turning it on doesn't perturb the other collectors. |

Each layer's marginal contribution is reported as Δ on the four headline metrics. Layers that move no metric by more than ±2% are reported as "no measurable effect" and discussed in Chapter 4.

---

## 5 — Gold-set protocol

- **Size:** 50 signals, stratified across 4 actor categories × 4 signal types (≥ 3 per cell where the corpus permits).
- **Sampling:** stratified-random from the `signals` table at the start of the evaluation window. Random seed recorded in `data/gold/seed.txt`.
- **Labelling:** by Anna only. Format documented in [`systems/evaluation/data/gold/labels.yaml.example`](../systems/evaluation/data/gold/labels.yaml.example).
- **Inter-rater (optional):** if supervisor agrees during the 2026-06-02 meeting, a 15-row sub-sample is labelled independently by the supervisor; Cohen's κ between the two label streams is the inter-rater agreement statistic.
- **Label revision:** each labelled signal is revisited once after a 7-day cooling-off period (intra-rater agreement). Cohen's κ between first and second pass reported.

---

## 6 — What counts as a *valid* run

For inclusion in the evaluation:
- `runs.status = 'ok'` (no exception in the graph or the loop)
- Audit folder materialised on disk with at least `config.json` + `signals.json`
- `signals.system` non-null on every produced row

Runs with `status = 'error'` are **counted toward token cost but not toward signal yield**, and the error category (network / LLM / Supabase / parser) is reported in §3.5.2 of the thesis.

---

## 7 — Departures from this pre-registration

Any deviation from this protocol after looking at the data must be:
1. Documented in [`docs/session_log.md`](session_log.md) with the date and rationale.
2. Flagged in Chapter 4.1.4 (Methodological and Technical Limitations).
3. Both the pre-registered and the post-hoc analyses reported (if applicable).

Acceptable categories of deviation:
- **Operational** (e.g. Supabase outage forced a cron miss) → report + use the next clean window.
- **Detected pre-registration error** (e.g. metric is undefined on the actual data) → fix here, regenerate, note the diff.
- **Discovered confound that the pre-registration didn't anticipate** → add as a §5.3 limitation, propose how a future replication would handle it.

Non-acceptable: changing the falsification thresholds after seeing the data.

---

## 8 — Locked references

The Supabase schema at evaluation freeze is captured in [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) at this commit. The signal taxonomy is the v0.4.0 schema in [`schema.yaml`](../systems/masfactory/masfactory_system/classification/schema.yaml). The evaluation harness is [`systems/evaluation/`](../systems/evaluation/). Every number cited in Chapter 3.5 must be reproducible by running `python -m eval_app.runner all` against the frozen Supabase snapshot at the §3 freeze timestamp.
