# Open questions for the bachelor thesis

A living document. Each entry has: **what the question is**, **why it matters**, **the candidate answer / current default**, and **what would change my mind**.

---

## 1. Evaluation

### Q1.1 — Gold-set size + stratification
**Question.** How many manually labelled signals are enough for the empirical classification-quality metric, and how should they be stratified?
**Why it matters.** Headline number in Chapter 3.5 (Empirical Results) is precision/recall against a hand-labelled gold. A too-small gold gives noisy estimates; a too-large gold doesn't fit in the calendar.
**Current default.** 50 signals, stratified across 4 actor categories × 4 signal types (≥ 3 per cell where the corpus permits).
**Would change my mind if.** Supervisor wants inter-rater reliability metrics (Krippendorff α / Cohen κ) computed against a second labeller — then the gold needs to be larger (≥ 100) so the agreement statistic isn't dominated by sampling noise.

### Q1.2 — Cross-system agreement metric
**Question.** What's the cleanest single number for "how much do System A and System B agree on what to keep?"
**Candidates.** (a) per-actor Jaccard over the set of `(source_url)` survivors; (b) per-actor Jaccard over `(dimension)` distributions; (c) Spearman correlation of per-actor `impact` scores; (d) confusion-matrix between the two systems' `signal_type` assignments on the *intersection* of signals both saw.
**Current default.** (a) per-actor Jaccard on `(source_url)` — most directly answers "are they finding the same things?". Supplemented with (c) for the impact-score correlation.

### Q1.3 — Cost normalisation for the headline efficiency metric
**Question.** "Output quality per token cost" needs a denominator. Free-tier Nemotron has list price ≈ 0; reporting `1/0` makes no sense.
**Candidates.** (a) absolute token count (input + output), no monetary conversion; (b) hypothetical paid-tier price (Nemotron Super 3 paid is $0.X / 1M tokens); (c) walltime per run.
**Current default.** (a) tokens — already in Supabase `token_usage` and reproducible without external price data.

### Q1.4 — A/B scope for the optional capability layers
**Question.** Five env-gated layers (embeddings, semantic dedup, consensus Critic, debate Critic, EPO OPS). Full factorial = 32 combinations; one-at-a-time = 5 + baseline = 6.
**Current default.** One-at-a-time. Each layer gets a dedicated weeklong cron window with audit folders tagged in `config_snapshot`. Marginal contribution reported as the delta vs baseline.
**Decision point for supervisor today.**

### Q1.4b — Stock validator as a credibility cross-check
**Question.** Should a "stock validator" component be added to both systems — e.g. when a public actor announces a major partnership, cross-check against the next trading day's stock-price movement as a market-validation signal?
**Why it matters.** The signalling-theory literature treats stock-price reaction as the *receiver-side* validation of a costly signal (Connelly et al. 2011 §receiver condition). Including this would add a quantitative validation leg the dashboard could use to weight signals.
**Current default.** Not implemented — supervisor decision pending.
**Open questions for the supervisor:**
- Which system(s): both, or only one? (Probably both, to keep the comparison clean.)
- Which API: Yahoo Finance (free), Alpha Vantage (free tier), or paid Refinitiv?
- What window: T+1 day, T+5 day, or both?
- Which actors qualify: only the publicly-listed ones (IonQ, D-Wave, Rigetti) — the Swiss actors are mostly private + government.
**Decision needed before implementation.** See [`feature-candidates.md`](feature-candidates.md) §Evaluation for the stock-data libraries.

### Q1.5 — Reproducibility audit
**Question.** Constructive research methodology asks for reproducibility. What's the operational definition for the thesis?
**Candidates.** (a) re-run two random runs verbatim and compare signal counts + dimensions; (b) full prompt + model + version replay; (c) just point at the git SHA + Supabase point-in-time and call it reproducible.
**Current default.** (a) — concrete and citable; the audit folder + `runs.config_snapshot` make it cheap. Reported as: "X% of signals re-emerge on re-run with identical settings; the gap is attributable to model non-determinism at temperature > 0."

---

## 2. Methodology framing

### Q2.1 — Constructive research vs Design Science Research vocabulary
**Question.** The disposition cites **Kasanen et al. (1993)** (constructive research) but later sections say **Design Science Research**. They're close cousins but the chapter language should pick one.
**Current default.** Constructive research throughout, since Kasanen et al. is named in the disposition.

### Q2.2 — Definition of "ideal architecture"
**Question.** SRQ4 asks for "the gap between ideal and implemented." But "ideal" relative to *what*? The full MASFactory + Hermes union? A literature-derived synthesis? A theoretical maximum?
**Candidates.** (a) a synthesised reference architecture combining the strongest patterns from MASFactory, Hermes, AgentOS, LogicGraph, MiroFlow; (b) the union of the two systems we actually built; (c) MASFactory's full feature set used as the reference because its paper is most architecturally complete.
**Current default.** (a). The literature review (§2.1.4) derives a synthesised reference; the gap analysis enumerates which patterns A and B each instantiate.

### Q2.3 — Are the two systems "competing" or "complementary"?
**Question.** Cross-system comparison frames them as competing on a single task. But Hermes is designed for long-running personalised assistance, MASFactory for graph-defined research pipelines. A fair comparison demands the SAME task — but is the task we built the right one for both?
**Current default.** The task is *deep-tech ecosystem signal collection on a fixed cadence*. We made deliberate design choices (cron-driven, batch-mode, no interactive prompts) so both systems are evaluated on identical inputs. The "is this the right shape for Hermes?" question becomes part of the gap-analysis discussion, not a confound.

---

## 3. Data + sources

### Q3.1 — Actor list freezing
**Question.** The 40-actor list is editable in Supabase (Anna can hand-edit `arxiv_query` and `notes`). When do we *freeze* it for the empirical evaluation?
**Current default.** Freeze the actor list two weeks before submission. Until then, additions/refinements ok; they're git-tracked via `data/raw/actors.yaml` and the Supabase upsert preserves user edits.

### Q3.2 — Public-data-only constraint
**Question.** The disposition restricts to publicly-available + citable data. Some Bing-News-aggregated articles are behind paywalls (FT, NZZ, Bloomberg). Do these still count?
**Current default.** Yes — the URL is citable even if the content isn't free. We record the URL + the snippet the aggregator surfaced (which is always free); the evidence_quote field is verbatim from that public snippet.

### Q3.3 — Time window for the corpus
**Question.** Headline ecosystem map = all signals ever, or signals in a rolling window?
**Current default.** Rolling 90-day window for the dashboard's "current state" view; full history available via the filter. Reports use a fixed 7-day window (daily) / 30-day window (weekly).

### Q3.4 — Wrong-signal correction policy
**Question.** When a wrong signal is spotted on the dashboard, what's the lifecycle?
**See dedicated strategy doc.** [`docs/wrong-signals-strategy.md`](wrong-signals-strategy.md).

### Q3.5 — Anna's parallel coding methodology (decision needed)
**Question.** Anna will mark signals as positive examples ("Parallelcodierung") to feed the systems. Three sub-decisions:
1. **Tool:** the website's flag button (in-app, lowest friction) vs ATLAS.ti (richer coding interface, more familiar to qualitative researchers) vs QualCoder (open-source, SQLite export). v0.4.2 ships the in-app flag (reason `correct_example`) which automatically becomes a few-shot exemplar for the Classifier prompt; this is the default until the supervisor prefers otherwise.
2. **Corpus subset:** every signal Anna reviews, or a stratified random sample (≥ 3 per actor-category × signal-type cell)? Stratified-random gives a more defensible thesis claim; comprehensive gives more examples for the Classifier.
3. **Timeline:** rolling (Anna labels as the cron produces signals each day) vs batched (one labelling session per week / fortnight). Rolling matches Kasanen's build-evaluate-refine loop; batched is less interruptive.
**Current default (v0.4.2):** in-app flag button + rolling labelling. Whichever signals Anna marks as `correct_example` automatically become Classifier exemplars on the next cron tick (via `classification.few_shot_examples_block()`).
**For supervisor:** confirm or amend.

---

## 4. Signal taxonomy

### Q4.1 — Extensions to Ehrenthal's coding scheme
**Question.** Two sub-categories (`funding_event`, `regulatory_recognition`) extend the paper's coded markers. Are they justified for the thesis?
**Candidate answer.** Yes — they sit in Ehrenthal's separate "Communication Categories" axis (Investor/Funding) and aren't present at all in the vendor-comms corpus (regulatory). Both are grounded in Suchman 1995 / Rieger et al. 2025 / Swiss public-sector context.
**Decision point for supervisor today.**

### Q4.2 — Asymmetric Ehrenthal % shares as a comparison baseline
**Question.** Ehrenthal et al. report per-marker % shares (76% roadmaps, 14% testimonials, etc.) for the vendor corpus. Our Swiss corpus likely shows very different shares (e.g. ETH / EPFL pull "publications" up, no "testimonials"). Is this divergence a *finding* or a *flaw*?
**Current default.** Finding. The thesis reports the divergence as a substantive result: Swiss public-sector actors use the same signal vocabulary as global private vendors, but with very different weights — and this difference is itself a signal about ecosystem maturity / category-membership.

### Q4.3 — Channels axis vs signal_types axis
**Question.** v0.4.0 keeps the v0.3.0 channel axis (capability / legitimacy) alongside the new signal_types axis. Two parallel taxonomies on the same row.
**Current default.** Both, because Ehrenthal's scheme is signal_type-only and the capability/legitimacy split is informative for the credibility-weighting story. The dashboard surfaces signal_type by default; channel is available as a secondary filter.

---

## 5. Architecture decisions worth flagging

### Q5.1 — System B's `register_signal` tool is a wide schema
**Question.** Hermes' AIAgent has to emit `actor_slug`, `source_url`, `source_kind`, `title`, `summary`, `evidence_quote`, `dimension`, `signal_type`, `is_technical`, `confidence` in one tool call. Free-tier Nemotron sometimes hallucinates fields.
**Current default.** Tool description spells out the required fields + valid enums. Persistence normalises legacy dim keys + auto-fills signal_type from dimension. Drop rate ≈ 5% per run.
**Would change my mind.** If drop rate goes > 15%, decompose into a chain of smaller tools (`stage_signal` → `classify_staged` → `submit_classified`).

### Q5.2 — Should we cite OpenRouter's free tier as a finding?
**Question.** The entire build runs on free-tier Nemotron-3-Super-120B-A12B. That's notable for a thesis on "cost-effective deep-tech research" — but also a confound (a paid model might give very different quality).
**Current default.** Mention as a *constraint* in §2.2.4 (Evaluation Framework) and report results with the explicit caveat "on this model." Don't claim model-agnostic findings.

---

## 6. Write-up

### Q6.1 — Chapter 3 vs Chapter 4 line
**Question.** Where does *"the system works"* (Chapter 3) end and *"what it means"* (Chapter 4) begin?
**Current default.** Chapter 3 reports the four empirical metrics (classification quality / inter-system agreement / token cost / reproducibility) as numbers + tables. Chapter 4 interprets them and synthesises across SRQ1-4.

### Q6.2 — How much code in the appendix vs the body?
**Question.** Thesis text typically caps technical detail. The schema YAML + key prompts + the SQL migration are central to the work but voluminous.
**Current default.** Body cites file paths and quotes 5-15 lines max per code excerpt. Appendix contains the full schema YAML, the Critic prompt (most-iterated artefact), and one full run's audit folder (anonymised).

---

## Resolved (kept for record)

- ~~Pick the underlying LLM model.~~ → Nemotron-3-Super-120B-A12B:free as main, Llama-3.3-70b:free as fallback. Both via OpenRouter.
- ~~Which signal classification scheme?~~ → Ehrenthal et al. 2026 four-signal scheme (v0.4.0 schema).
- ~~How to distinguish wrong attribution from wrong dimension?~~ → Critic's DROP RULES separate them: actor-relevance first, then dimension-evidence match.
- ~~Where does the dashboard live?~~ → [https://mas-deeptech-research.cloud](https://mas-deeptech-research.cloud) (Hostinger VPS, Caddy auto-HTTPS).
- ~~Streamlit or React?~~ → React (Next.js 14 App Router + TypeScript), backed by FastAPI. Streamlit container kept as transitional fallback.
