# Threats to validity

Draft for **Chapter 4.1.4 (Methodological and Technical Limitations)** of the thesis. Catalogues threats to construct, internal, external, and conclusion validity — and, for each, what was done to mitigate it and what remains as a limitation.

Validity types follow Cook & Campbell (1979) / Shadish, Cook & Campbell (2002) as standard for thesis-level empirical software-engineering work.

---

## 1 — Construct validity

*"Are we measuring what we think we're measuring?"*

### 1.1 — "Signal classification quality" as a thesis-construct vs the precision/recall numbers

The disposition uses "classification quality" as a single construct. Our operationalisation splits it into four sub-metrics (4-way `signal_type` F1, 19-way `dimension` F1, Critic keep-precision, Cohen's κ vs a gold set). The mapping is defensible — each sub-metric captures a different facet — but it's a deliberate construction. The thesis is honest about this: §3.5 reports the four numbers separately rather than collapsing them.

**Mitigation:** The pre-registration in [`docs/pre-registration.md`](pre-registration.md) commits to the four sub-metrics before looking at the data.

### 1.2 — "Costly vs cheap" signal classification reduces to a 3-way axis

The schema's `signal_cost ∈ {high, medium, low}` is our operationalisation of Spence's (1973) credibility-mechanism. Real costliness is continuous (filing a patent ≠ funding $X for x ∈ ℝ); we discretise to three bins for tractability. This is the standard concession in the signalling-theory literature (Connelly et al. 2011) but worth flagging.

**Mitigation:** Per-dimension `weight` × `signal_cost` multiplier in scoring.py gives finer-grained credibility-weighted impact than the 3-bin axis alone.

### 1.3 — Inter-system agreement = Jaccard on `source_url` ignores semantic equivalence

Two signals about the *same event* with different URLs (e.g. one news article + one press release) count as disagreement. Semantic dedup via pgvector cosine (`MASF_SEMANTIC_DEDUP`) addresses this only after persistence; the inter-system metric runs on the pre-dedup persisted set.

**Mitigation:** Section 3.5.3 also reports a *semantic* inter-system agreement: Jaccard over the *clustered* signal set (cluster = cosine similarity ≥ 0.92 on the BGE embedding). The two numbers bracket the construct.

### 1.4 — "Token efficiency" = volume only

Reported as *signals persisted per 1 000 tokens*. A system producing twice as many signals per token at half the precision is **not** actually more efficient. The thesis's headline efficiency number combines this volume leg with the classification-quality F1 (§3.5.4 reports both ingredients side-by-side).

---

## 2 — Internal validity

*"Could something else be causing the observed differences between the two systems?"*

### 2.1 — Model choice is held constant but the *prompt* is not

Both systems route through OpenRouter's free-tier `nvidia/nemotron-3-super-120b-a12b` (with `meta-llama/llama-3.3-70b-instruct` as fallback). The prompts, however, differ substantially: System A has 5 specialised Agent prompts; System B has one core-loop prompt + 4 `SKILL.md` skill files. Differences in output may be attributable to prompt design rather than architecture.

**Mitigation:** The prompts are versioned in git; the audit folder records the prompt that produced each run. The thesis cannot fully separate "architecture effect" from "prompt effect" — this is reported as a limitation, with a recommendation that a follow-up study fix the prompts identically and compare only the orchestration layer.

### 2.2 — Free-tier rate limits as a confound

Both systems share the OpenRouter free quota. Rate-limit failures fall back to the secondary model, which may produce different output. The `FailoverLegacyOpenAIModel` records which model produced each call in `audit_log`.

**Mitigation:** Token-usage rows record `model_name` separately. Runs where the fallback was used > 10% of calls are flagged in §3.5.2 and excluded from the headline metric (reported separately as "secondary-model runs").

### 2.3 — Schema v0.3.0 → v0.4.0 migration boundary

Half of the historical signal corpus was classified under the v0.3.0 9-dimension scheme; the v0.4.0 19-dimension scheme is used going forward. The migration mapping is deterministic (see [`docs/signal-taxonomy.md`](signal-taxonomy.md) §v0.3.0→v0.4.0 mapping) but introduces one-to-one rewriting that is *not* the same as the Classifier choosing freshly under v0.4.0. A v0.3.0 `infrastructure_or_facility` always becomes `hpc_collaborations` even if `cloud_platform_listings` would have been a better v0.4.0 fit.

**Mitigation:** `dimension_legacy` is preserved on every migrated row. The thesis evaluates **only** post-migration signals (window starts 2026-06-09 = 8 days after the schema flip) so the Classifier has had time to pick from the full v0.4.0 set.

### 2.4 — Critic-strictness change mid-evaluation

The v0.4.0 Critic (commit `f8399af`) introduced explicit DROP RULES. Signals pre-dating this commit were filtered by the v0.3.0 Critic (laxer). Mixing the two yields apples-to-oranges per-system counts.

**Mitigation:** Evaluation window starts after the Critic change. All counted signals were filtered by the v0.4.0 Critic.

### 2.5 — Daily-cron correlation with news cycles

Both systems run within 3 hours of each other (System A 02:00 CET, System B 05:00 CET). A breaking quantum news story between 02:00 and 05:00 will be visible to System B but not System A on the same date. Per-actor Jaccard absorbs this naturally (it's symmetric over the union), but raw signal counts are mildly asymmetric.

**Mitigation:** Reported as a footnote in §3.5.1. The headline metric (Jaccard) is unaffected.

---

## 3 — External validity

*"Do the results generalise beyond the Swiss-quantum-2026 context?"*

### 3.1 — Swiss-only actor list

The 40-actor cohort is exclusively Swiss. Ehrenthal et al. (2026) study six global private vendors (D-Wave, IonQ, Pasqal, Rigetti, Xanadu, Infleqtion). The signal taxonomy was validated on their dataset, not ours. Differences between our Swiss share-of-signals and theirs (e.g. our `publications` likely > 7%, our `testimonials` likely ≪ 18%) are findings, not flaws — but the *Swiss-ness* of the empirical results limits direct generalisation to e.g. a Singapore-quantum-ecosystem replication.

**Mitigation:** Thesis explicitly frames findings as "Swiss-ecosystem 2026" rather than "deep-tech in general." Section 5.3 (Future Research Directions) recommends replication on a non-Swiss cohort as the first follow-up.

### 3.2 — Quantum-computing-only

The methodology is designed to generalise to any "noncommensurable performance" deep-tech market (the disposition lists biotech, fusion, novel-materials as candidates). But the operational evaluation is on quantum only. Generalisation to other deep-tech is a *claim*, not a *demonstration*.

**Mitigation:** SRQ 4 (gap analysis) explicitly discusses transferability. Section 5.3 enumerates the schema changes needed for biotech (e.g. clinical-trial-phase as a sub-category under `future_trajectory`).

### 3.3 — Model-specific findings

All numbers are produced by Nemotron-3-Super-120B-A12B (primary) + Llama-3.3-70B (fallback). Different models may have different cost/quality trade-offs.

**Mitigation:** §2.2.4 reports results "on this model" with the explicit caveat. The architecture allows model switching via env var (`MASF_MODEL_MAIN`, `HRM_MODEL_MAIN`); a follow-up study could replicate with paid-tier Claude Opus or GPT-4o and report the model effect.

### 3.4 — Time-bounded freshness

Many signals reference time-sensitive content (cloud-platform listings come and go; roadmaps are dated). The thesis's frozen-for-defence snapshot is at 2026-07-07; a reader running the harness in 2027 will see different (likely smaller, due to URL rot) numbers.

**Mitigation:** Audit folders preserve raw documents; the frozen snapshot is `data/eval/2026-07-07T<...>/` and can be replayed offline. Reproducibility metric (§3.5.4) calibrates the per-week churn.

---

## 4 — Conclusion validity

*"Are the statistical / inferential conclusions justified?"*

### 4.1 — Small N (40 actors)

The actor cohort is small by quantitative-research standards (N = 40). Per-actor metrics with macro-aggregation are unbiased but high-variance. Reporting 95% bootstrap CIs on the inter-system Jaccard mitigates over-confident conclusions.

**Mitigation:** Bootstrap CIs reported alongside every macro number. Effect-size claims (e.g. "system A is more token-efficient than system B") are made only when the CI does not cross the falsification threshold.

### 4.2 — Single annotator on the gold set

If only Anna labels the gold set, the inter-rater-reliability check (Cohen's κ between annotators) is unavailable. Without it, the κ-vs-system metric collapses to "Anna agrees with herself" (which is the intra-rater κ).

**Mitigation:** If the supervisor labels a 15-row sub-sample, inter-rater κ is reported. If not, the thesis reports intra-rater κ (second-pass after 7 days) instead — and explicitly notes that inter-rater agreement is unavailable.

### 4.3 — Cherry-picking among the optional capability layers

Five env-gated layers × independent A/B = 5 chances to find a "winner." Family-wise error rate inflates with multiple comparisons.

**Mitigation:** Each layer's marginal contribution is reported descriptively. No formal multiple-comparison correction is applied (the N is too small for it to be informative); instead, the thesis is explicit that *any single layer producing a < 5% improvement is reported as "no measurable effect"* — making the criterion strict enough that family-wise inflation is unlikely to mint false positives.

### 4.4 — Cron non-determinism vs prompt iteration

The prompt has been iterated during development (most recently in commit `b6e3ed3` per task #67 — Wei et al. 2022 / Khot et al. 2022 / Reynolds & McDonell 2021 patterns added). Numbers from runs before that change are not comparable to numbers from runs after.

**Mitigation:** Evaluation window starts AFTER the last prompt change. Audit folders carry the git-SHA-equivalent (prompt hash) recorded in `config_snapshot`.

---

## 5 — Compound threats

Two threats stack and deserve their own discussion:

### 5.1 — The two systems were designed for different *kinds* of tasks

System B (Hermes Agent) is canonically a *long-running personal-assistant* agent. System A (MASFactory) is a *cron-driven batch graph*. Running both on the same batch-cron task may underweight Hermes's design strengths. The comparison is therefore *"how well does each architecture survive being forced into a batch task it wasn't natively designed for"* — not *"which is the better architecture in general."*

**Reported as:** Section 4.1.2 (Comparative Evaluation) opens with this framing. The headline finding is task-conditional.

### 5.2 — The evaluator (Anna) is also the system designer

I built the systems, the schema, the gold set, and the evaluation harness. The standard mitigation (independent evaluator) isn't available within a BSc thesis scope.

**Reported as:** Section 4.1.4 (Methodological Limitations) explicitly. The pre-registration ([`docs/pre-registration.md`](pre-registration.md)) is the strongest mitigation available — committing to falsification thresholds before looking at the data limits the post-hoc adjustment surface.

---

## Summary table

| Threat | Type | Mitigation | Residual concern |
|---|---|---|---|
| Quality construct splits into 4 metrics | Construct | Pre-registration | Composite quality remains a judgement call |
| URL Jaccard ignores semantic equivalence | Construct | Report URL + cosine-cluster Jaccard | Cluster threshold (0.92) chosen by hand |
| Prompts differ between systems | Internal | Audit-folder prompt logs | Cannot fully separate architecture from prompt effect |
| Rate-limit fallback to secondary model | Internal | `model_name` per token row | Heavy fallback-runs reported separately |
| Schema migration boundary | Internal | Window starts post-migration | None for in-window signals |
| Critic strictness change | Internal | Window starts post-change | None for in-window signals |
| Swiss-only cohort | External | Explicit framing in §3 | Generalisation is a claim, not a demonstration |
| Quantum-only domain | External | §5.3 discusses transfer | No empirical evidence outside quantum |
| Free-tier Nemotron only | External | Architecture supports model swap | Numbers are model-conditional |
| Time-bounded freshness | External | Frozen snapshot | Replication in 2027 will differ |
| Small N (40 actors) | Conclusion | Bootstrap CIs on every macro | Variance is irreducible at this N |
| Single annotator | Conclusion | Intra-rater κ + (optional) inter-rater | If supervisor doesn't label, only intra-rater available |
| Multiple capability-layer comparisons | Conclusion | Strict 5% threshold; no formal correction | Family-wise error rate higher than for a single comparison |
| Cron vs prompt iteration | Conclusion | Window starts post-iteration | None for in-window signals |
| Architectural fit asymmetry | Compound | §4.1.2 framing | Hermes design strengths under-tested |
| Designer = evaluator | Compound | Pre-registration | Inherent to BSc-thesis scope |
