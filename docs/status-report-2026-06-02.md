# Bachelor thesis — status report

**Student:** Anna Geiser
**Programme:** BSc, FHNW
**Supervisor:** Prof. Dr. Joachim Ehrenthal
**Client:** Prof. Dr. Yannick Suter (FHNW)
**Working title:** *Multi-Agent Systems for Ecosystem Mapping Under Noncommensurable Performance: Computational Signal Processing in Swiss Quantum Computing*
**Reporting period:** 2026-04-21 → 2026-06-02 (6 weeks)
**Live artefact:** [https://mas-deeptech-research.cloud](https://mas-deeptech-research.cloud)
**Repository:** [github.com/annageiser/mas-deeptech-research](https://github.com/annageiser/mas-deeptech-research) (public, `main` branch)

---

## Headline

Both multi-agent systems are running on cron in production. The signal classification schema is now aligned **1:1 with your four-signal scheme** (Ehrenthal et al. 2026); historical signals were migrated without data loss. The public website (FastAPI + Next.js 14) renders the live corpus at the URL above. The infrastructure is feature-complete for the empirical evaluation; the remaining six weeks of the thesis can be calendar-time + analysis without further code work (modulo small UX polish).

---

## What shipped in the past 6 weeks — mapped to the four sub-research questions

### SRQ 1 — Signal types and classification schema

- **Signal classification schema v0.4.0 — aligned with Ehrenthal et al. (2026) four-signal scheme.** Replaced the v0.3.0 nine ad-hoc dimensions with the paper's official taxonomy: 4 top-level signal types (`legitimacy`, `customer_cocreation`, `community_ecosystem`, `future_trajectory`) × 19 sub-categories. **17 of the 19 sub-categories match the paper verbatim**; the 2 extensions (`funding_event`, `regulatory_recognition`) are flagged `extension: true` in the YAML and grounded explicitly in Suchman (1995) / Rieger et al. (2025) — they exist to cover the Swiss public-sector slice (SNF, Innosuisse, federal quantum strategy) that the paper's vendor-only dataset doesn't sample.
- **Layered axes on every sub-category** (Spence 1973 / Connelly et al. 2011): `signal_cost` ∈ {high, medium, low} and `observability` ∈ {high, medium, low}. Both feed the credibility-weighted impact score on the dashboard.
- **Migration without data loss.** Idempotent SQL block rewrites the 9 legacy keys to the 19 new keys in place and backfills `signal_type`. Original value preserved in `signals.dimension_legacy` so pre-migration analyses remain reproducible.
- **Single source of truth.** `classification/schema.yaml` is loaded at runtime by the agents AND served verbatim via `/api/meta` to the public site. The dashboard cites exactly what the agents run.
- **Documentation:** the full taxonomy + extension justification + literature mapping is in [`docs/signal-taxonomy.md`](signal-taxonomy.md) — a thesis-citable reference.

### SRQ 2 — Ideal multi-agent architecture (literature)

- **Two architectural philosophies operationalised side-by-side.** Container A is the **MASFactory orchestration-centric** path (Liu et al. 2026): a directed graph of 7 conceptual nodes (Planner → Retriever → Extractor → Classifier → Critic → Analyst → Persistence) with three helper CustomNodes and a per-actor `Loop`. Container B is the **Hermes memory-and-skill-centric** path (Nous Research 2025): a single long-running `AIAgent` loop with SQLite procedural memory, four `SKILL.md` skill files (`arxiv` / `scrapling` / `parallel-cli` / `research-paper-writing`), a Tools Registry, and a single Provider abstraction. Both systems write to the same Supabase schema so cross-system comparison stays clean.
- **Optional capability layers, all env-gated and off by default**, so the baseline cron runs unchanged and each can be A/B'd independently:
  - **Self-consistency Critic** (Wang et al. 2023) — `MASF_CRITIC_CONSENSUS_PASSES=3` swaps the single Critic for 3 independent Critics + a majority vote.
  - **Multi-agent debate Critic** (Du et al. 2023) — `MASF_CRITIC_DEBATE_ROUNDS=1` adds 3 debate Agents on top of the consensus chain; each sees the others' verdicts and revises.
  - **pgvector semantic dedup** — `*_SEMANTIC_DEDUP=1` queries the existing corpus by cosine similarity (`find_similar_signals` RPC) and drops near-duplicates.
  - **768-dim BGE embeddings** — `*_EMBEDDINGS=1` populates the `signals.embedding` vector column at insert time.
  - **EPO Open Patent Services** — `EPO_OPS_CONSUMER_KEY/SECRET` activates patent ingestion (fills the disposition's reserved `source_kind='swissreg'`).

### SRQ 3 — Implementable components within thesis scope

- **Seven Docker containers on one Hostinger VPS, one Supabase, one OpenRouter key.** Containers A + B (the two MAS), C (reports synthesis), D (legacy Streamlit, transitional), E (Caddy reverse proxy with auto-HTTPS), F (FastAPI), G (Next.js 14 frontend). Cron schedule in Europe/Zurich timezone: 02:00 System A + daily report; 05:00 System B + daily report; Sunday 08:00 three weekly reports.
- **Five-collector funnel per actor**: arXiv + actor website (RSS-discovery + depth-2 scrape) + Google News + Bing News (press-release-flavoured query) + EPO patents. Limits doubled in v0.4.0 (10 per collector default). Queries widened beyond plain `quantum` to `quantum OR qubit OR QKD` to catch subfields.
- **Tighter Critic on the way out** (v0.4.0) — explicit DROP RULES in priority order: actor-relevance → quantum-relevance → dimension-evidence match → confidence ≥ 0.45 → boilerplate → duplicates. Explicit framing: precision-over-recall now that the funnel is wider.
- **Public website (FastAPI + Next.js 14) at [https://mas-deeptech-research.cloud](https://mas-deeptech-research.cloud)** — 11 typed pages including Methodology (cites the same `schema.yaml` the agents read), Signalling theory, Impact leaderboard, Ecosystem, per-actor Spotlight, Compare-two-actors, System-A-vs-System-B, Knowledge graph (dependency-free SVG with hover inspector showing per-edge meaning), Signals explorer, Reports browser.
- **Full audit trail** — per-run folder `data/raw/runs/<CET-iso>__<system>/` with config snapshot, raw documents, per-stage JSON, brief, token tally, dropped-hallucinations + dropped-cross-actor + (if on) embeddings_summary + semantic_dedup + critic_consensus_audit.

### SRQ 4 — Gap between ideal and implemented + transferability

- **Comparative-validity invariant enforced.** Systems A and B share no Python code beyond the data contract (the Supabase schema). Containers C/D/F/G *read* from both but never *write*. The "which architecture wins" question is therefore answerable on the empirical evidence, not on a coincidence of shared utility code.
- **Deliberate omissions catalogued for the gap analysis** ([`docs/methodology.md`](methodology.md) §Deliberate omissions): Telegram gateway on System B (`TelegramGatewayStub` no-op exists), R≥2 debate rounds, authentication on the public site, retirement of the legacy Streamlit container. Each is honest material for the gap-analysis chapter.

---

## Currently open

Nothing is blocking the empirical evaluation. The following are known limitations or in-flight cleanups:

1. **Some classified signals are visibly wrong on the dashboard.** Mostly mis-attributions (the actor mentioned in a press item isn't actually the *subject* of that item) and a small number of off-topic items. The v0.4.0 Critic strictness already addresses this for *new* signals; for *existing* signals a separate cleanup pass is needed (a SQL audit + a "flag wrong" workflow — design doc in [`docs/wrong-signals-strategy.md`](wrong-signals-strategy.md)).
2. **No manual gold-set yet.** The empirical evaluation's precision/recall and inter-system-agreement metrics require ~50 hand-labelled signals. Not started.
3. **No EPO OPS credentials configured on the VPS yet.** The patent collector is code-complete and tested; it silently returns `[]` until `EPO_OPS_CONSUMER_KEY/SECRET` are added to `.env`. Free registration takes ~5 minutes.
4. **Weekly thesis report still includes git commit hashes** (e.g. `a0e0fdee06901bb...`). Cosmetic — a one-line fix to use `git log --format=%s` instead, on the to-do list for this week.
5. **Empirical-evaluation data thin so far.** Cron has been running daily for ~2 weeks; the thesis evaluation reads on a ≥ 4-week window for meaningful comparisons. Just needs calendar time.

---

## Next steps (next ~4–6 weeks)

| When | Action |
|---|---|
| This week | Strip git hashes from weekly report; flip the website's primary classification axis from 19 dimensions to your 4 signal types (drill-down to dimensions retained); register EPO OPS keys + enable patent collection on the VPS. |
| Week of 2026-06-09 | Hand-label a ~50-signal gold set from the existing Supabase corpus (stratified across actor categories + signal types). |
| Week of 2026-06-16 | Compute the four headline empirical metrics: classification quality vs gold set, inter-system agreement (cross-system Jaccard per actor), output quality per token cost (token_usage × gold-set scoring), reproducibility audit (re-run two runs verbatim). |
| Week of 2026-06-23 | Enable the optional capability layers one at a time (embeddings → semantic dedup → consensus Critic → debate Critic) on dedicated runs so the thesis can report the marginal contribution of each. |
| Week of 2026-06-30 | Draft Chapter 3 (Empirical Analysis) and the gap-analysis subsection of Chapter 4 from the audit data. |
| Final two weeks | Discussion + Conclusion chapters; final write-up; submission. |

---

## Decision points for today's meeting

1. **Schema extensions.** I added two sub-categories (`funding_event`, `regulatory_recognition`) to your four-signal scheme to cover the Swiss public-sector slice. Both are flagged `extension: true` so the thesis can A/B with the exact paper taxonomy. **Are you comfortable with these extensions?** Alternative: drop them and force every funding event into either `awards` or `industry_partnerships`.
2. **Gold-set labelling protocol.** I plan to hand-label ~50 signals stratified across actor categories and signal types, with one re-label round to compute intra-rater agreement. **Do you want to label a sub-sample yourself to compute inter-rater agreement?**
3. **Capability-layer A/B scope.** Each of the 5 optional layers (embeddings, dedup, consensus Critic, debate Critic, patents) costs LLM tokens or compute. **Do you want full factorial A/B (32 combinations) or one-at-a-time?** I'd recommend one-at-a-time for the thesis.
4. **Comparative metric for the headline cross-system comparison.** Current plan is *"surviving signals per 1k LLM tokens"* on a fixed actor cohort. **Any alternative you'd weight more heavily?**

---

## Quick-reference links

| Resource | URL |
|---|---|
| Live website | [https://mas-deeptech-research.cloud](https://mas-deeptech-research.cloud) |
| Signal taxonomy reference | [`docs/signal-taxonomy.md`](signal-taxonomy.md) |
| Methodology | [`docs/methodology.md`](methodology.md) |
| Architecture | [`docs/architecture.md`](architecture.md) |
| Open questions | [`docs/open-questions.md`](open-questions.md) |
| Repository | [github.com/annageiser/mas-deeptech-research](https://github.com/annageiser/mas-deeptech-research) |
