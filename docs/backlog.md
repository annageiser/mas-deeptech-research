# Backlog — thesis-scope features, methodology work, and known bugs

This is the canonical backlog for the BSc thesis. **Items are never deleted.** When something ships, it gets marked `[DONE vX.Y]` so the historical decision trail stays intact. The strategic backlog and the bug list live in the same document on purpose — a bug deferred is a deliberate choice, same as a feature deferred.

For tool/library evaluation see [`feature-candidates.md`](feature-candidates.md). For session-by-session iteration log see [`iterations/`](iterations/). For supervisor-meeting open questions see [`open-questions.md`](open-questions.md).

Format: MoSCoW priorities first, then a Bugs list, then a long-form "strategic" section with acceptance criteria.

---

## MoSCoW

### Must Have

- [ ] **M.1** Detect duplicated signals per system. Need a deterministic + a semantic dedup pass before the comparison page numbers can be trusted. We have content-hash exact dedup (since v0.4.4) and an optional pgvector semantic dedup (since v0.4.0, `MASF_SEMANTIC_DEDUP`). The "Must Have" is to **turn semantic dedup ON in production** and run a one-time backfill to remove existing duplicates from the historical corpus.

### Should Have

- [x] **S.1** Login (Caddy basic auth, single role) — `[DONE v0.4.4]`. Site-wide basic auth, user `anna`. Caused the v0.4.15–v0.4.17 reload-vs-restart cascade.
- [ ] **S.2** Two-tier login (admin + user roles) — see § A.1 below. Task #98.
- [ ] **S.3** Signal-judgement page for the admin role. Admin can mark each AI-collected signal as `correct` / `wrong` / `ambiguous` directly from the UI. Persists to `signal_flags` (already exists since v0.4.2) and re-renders the row with a coloured badge. Foundation for E.1 learning loop.
- [ ] **S.4** Separate page for human-in-the-loop:
    - [ ] **S.4a** Judges the signals collected by the AI (overlap with S.3 — same UI, different mode)
    - [ ] **S.4b** Lets Anna add manually-collected signals so the systems can learn from them. Becomes the C.1 gold-standard set (task #102).

### Could Have

- [x] **C.1** Dark mode — `[DONE v0.4.2 era]`. ThemeToggle.tsx in `systems/web/src/components/`.
- [ ] **C.2** Mobile / device adaptability. The Next.js stack uses CSS but no responsive breakpoints yet. Site looks fine on desktop, breaks on phone-width.
- [ ] **C.3** Stock validator integration — see § F.2 below. Task #110.
- [ ] **C.4** Sentiment score per signal. Run a tiny sentiment-classifier (free, e.g. `cardiffnlp/twitter-roberta-base-sentiment-latest` via HuggingFace inference free tier) on `summary + evidence_quote`. Adds a `sentiment` column to signals. Could feed into the stock-validator's "abnormal returns" comparison.

### Will Not Have (for this thesis window)

**WN.1 — Multi-skill pipeline for Hermes (mirror System A's 7-agent graph inside System B).**

Considered 2026-06-23 after Mistral Nemo solved the empty-signal issue. The idea: author separate Hermes skills (`planner.md`, `retriever.md`, `extractor.md`, `classifier.md`, `critic.md`, `analyst.md`) and orchestrate them sequentially from `collect_all_actors.sh`, replicating System A's explicit-graph decomposition inside System B's runtime.

Technically feasible. Hermes supports multiple skills and the shell wrapper can chain invocations.

**Why dropped:** doing this would erase the architectural contrast that the thesis's central research question depends on. The two-system design is built on the premise that A and B implement DIFFERENT architectures (explicit graph vs autonomous single-loop). If System B is rebuilt as a multi-step pipeline that mirrors A, the comparison in §4.1 collapses — both systems would have the same architecture, the "architecture matters" finding becomes trivially circular, and the four architecture-attributable differences documented in §4.1.2 (signal-yield, signal-mix, attribution-accuracy, parser-vs-model-robustness) lose their evidential weight.

System B's lower signal yield is not a defect to engineer away — it is the empirical finding that an autonomous single-loop architecture makes different trade-offs than an explicit-graph architecture on the same task. Recording the gap is the contribution.

If signal yield on System B needs to improve without breaking the architectural identity, the right levers are (a) richer single-skill prompt engineering — done in v0.4.27 and v0.4.29 — (b) a stronger underlying model — done in v0.4.36 with Mistral Nemo paid — and (c) a longer per-actor time budget. None of those changes the architecture.

Revisit only if the thesis pivots to a different research question (e.g. "how do we engineer the highest-yielding multi-agent system?" rather than "how does architectural choice shape behaviour?").

---

## Bugs

Reported by Anna 2026-06-11. Each has a working hypothesis and the next diagnostic step. None are deal-breakers; they're polish issues for the defence-ready website.

### Bug 1 — Signal Type not registered

**Symptom:** some signals in Supabase have empty / NULL `signal_type`.

**Hypothesis:** Schema has the column (since v0.4.0 migration). New hermes rows always populate it (v0.4.4 persister validates `signal_type ∈ VALID_SIGNAL_TYPES`). MASFactory rows have it backfilled from `dimension` via the v0.4.0 SQL block. The remaining NULLs are likely **pre-v0.4.0 rows that the backfill SQL didn't match** (the rewriting table only handles known v0.3.0 dimensions).

**Next step:**
```sql
SELECT signal_type, count(*) FROM signals GROUP BY signal_type ORDER BY count(*) DESC;
```
If the NULL bucket has rows, run the v0.4.0 backfill block once more (idempotent, see `docs/migrations.md`). If specific dimensions don't map, add them to the rewriter.

### Bug 2 — Reports not on the website / Daily Reports missing since 10th

**Symptom:** `/reports` page doesn't show recent daily reports. Specifically: from 2026-06-10 onwards (System B) and "onwards (both systems)".

**Hypothesis:** Two sub-issues:
1. **Hermes daily report**: the host crontab `/etc/cron.d/mas-deeptech-research-hermes` was installed today (2026-06-11 evening). First fire is **tomorrow at 05:00 Europe/Zurich**. Before then, no Hermes daily report file exists. This isn't a bug — it's first-deploy waiting.
2. **MASFactory daily report after 2026-06-10**: This would be a bug. From `/var/log/reports.log` we DID see a 2026-06-10 masfactory daily report write. But Anna says daily reports are missing from the website too — possible causes: API endpoint not seeing the bind-mounted file, or the website's reports list is filtered too narrowly.

**Next step:**
```bash
ls -la /opt/mas-deeptech-research/data/reports/daily/      # what files exist?
docker compose exec api ls -la /data/reports/daily/        # what does the api container see?
curl -s http://localhost:8000/api/reports | head -50       # what does the API return?
```
Check that the bind-mount `./data:/data:ro` in docker-compose.yml is still active and the api container can read the new dirs.

### Bug 3 — Signals page: some signal types not labelled

**Symptom:** `/signals` page shows some signal-type cells without colour or label.

**Hypothesis:** Pre-v0.4.0 rows have `signal_type` values that aren't in our current 5-value taxonomy. The legacy sub-dimensions (e.g. `defense_engagement` as a top-level type, not as a `dimension`) wouldn't match the label dictionary in `systems/api/api_app/labels.py`.

**Next step:**
```sql
SELECT signal_type, count(*) FROM signals
GROUP BY signal_type
ORDER BY count(*) DESC;
```
Cross-reference the distinct values against the `SIGNAL_TYPE_LABEL` map. For anything not in the map, either (a) backfill the row to a valid value, or (b) add a fallback label "(legacy)" + grey colour.

### Bug 4 — Don't use Firecrawl / OpenRouter fallback (credit concerns)

Not exactly a bug — a config preference. Firecrawl is currently tried first by upstream's `web_tools.py` if `FIRECRAWL_API_KEY` is set in `.env`. Your free Firecrawl credits will eventually deplete and the agent will transparently fall through to ddgs (DuckDuckGo, unlimited free). To force-skip Firecrawl immediately:

```bash
sed -i 's/^FIRECRAWL_API_KEY=/# FIRECRAWL_API_KEY=/' /opt/mas-deeptech-research/.env
docker compose restart hermes   # or wait for next cron
```

The MASFactory OpenRouter `MASF_MODEL_FALLBACK=meta-llama/llama-3.3-70b-instruct:free` is also free — no credits consumed if that fires. Confirmed in audit `:free` policy v0.4.8.

---

## Hermes skills to activate

The upstream image bundles 75 skills (saw the full list at first boot). We currently load `collect-swiss-quantum-signals,arxiv`. Skills Anna wants enabled, ordered by relevance to the thesis:

- [ ] **company-research** — structured per-company dossier; would pair well with the actor spotlight page
- [ ] **blogwatcher** — RSS/blog monitoring (already an item in § B.2 below)
- [ ] **arxiv** — `[DONE v0.4.14]` — loaded via `--skills collect-swiss-quantum-signals,arxiv`
- [ ] **research-paper-writing** — could help generate the per-actor briefs that go into the markdown reports
- [ ] **scrapling** — fallback page-scraping when ddgs snippets are insufficient
- [ ] **searxng-search** — self-hosted meta-search; only matters if we set up a SearXNG instance (extra infra)
- [ ] **Academic Deep Research** — multi-step literature pull; potentially overlaps with `arxiv` skill but goes deeper
- [ ] **Academic Paper** — paper-formatting skill; mostly relevant to the thesis-writing workflow, not the cron

**Implementation:** add slug-list to the `--skills` flag in `systems/hermes/scripts/collect_all_actors.sh`. Each new skill is a comma-separated entry. No image rebuild needed since skills are in the upstream image.

```bash
# Conservative addition that doesn't blow up token budgets:
--skills collect-swiss-quantum-signals,arxiv,blogwatcher,company-research,scrapling
```

---

## Strategic backlog (long-form, with acceptance criteria)

This is the unchanged sections A–I from the previous backlog version, kept for the acceptance criteria and the rationale.

### A — Authentication & access control

#### A.1 — Two user groups on the public site (admin + user)

Currently the Caddy basic-auth gate is a single role (`anna`, full access). Split into admin (`anna`) and user (read-only). Implementation: either two basicauth blocks in Caddyfile or migrate to FastAPI middleware on the API layer. **Acceptance:** non-admin user can read every page but cannot POST to state-mutating endpoints; the `/signals` page hides "Report wrong" button for non-admins. **Task #98.**

### B — Coverage expansion (RSS-based, token-efficient)

#### B.1 — Quantum Insider RSS

Add https://thequantuminsider.com/category/daily/ to `data/raw/rss_feeds.yaml`. **Acceptance:** ≥5 signals/week from this source. **Task #99.**

#### B.2 — Hermes `blogwatcher` skill

Load alongside our skill. **Acceptance:** at least one cron run produces blogwatcher-attributed signals. **Task #100.**

#### B.3 — Coverage measurement

`signals/actor/week` per source_kind on `/compare`. **Task #101.**

### C — Methodology framing

#### C.1 — Gold-standard human coding

Anna manually classifies signals for 5 actors. **Task #102.** This is the data source for S.4b above.

#### C.2 — Atlas.ti framing in the LLM prompts

**Task #103.**

#### C.3 — Explicit project goal statement

"Spezifiziere möglichst wenig, krieg möglichst viel heraus." **Task #104.**

### D — Defense ambivalence

#### D.1 — Research the phenomenon

D-Wave / Anthropic Mythos examples. **Task #105.**

#### D.2 — Actor-level marker, not signal

`actors.defense_ambivalence_marker boolean`. **Task #106.**

#### D.3 — Keyword filter

"national security" / "classified" / "ITAR" / "EAR". **Task #107.**

### E — Learning loop

#### E.1 — Miss diagnosis

When gold-standard surfaces a missed signal, classify why (not-searched / extracted-but-dropped / extracted-but-misclassified) and feed into next prompt iteration. **Task #108.**

### F — Stakeholder actionability

#### F.1 — Persona views

`/personas` page with Investor / Researcher / Enthusiast / Supervisor toggles. **Task #109.**

#### F.2 — Stock validator

`yfinance` for listed actors; abnormal returns around signal dates. **Task #110.** Re-opens deferred task #86.

### G — GitHub tooling research

#### G.1 — Continuous audit

QualCoder (https://github.com/ccbogel/qualcoder) is the current candidate. **Task #111.**

### H — Iteration documentation

#### H.1 — One iteration doc per `v0.4.x:` commit

Continuous. The 2026-06-10/11 Phase B cascade (v0.4.4 → v0.4.18) is the test case — every doc landed.

#### H.2 — Documentation update (catch-all)

The whole docs tree was last comprehensively reviewed during the v0.4.3 status report. After v0.4.18 there are new sections that haven't been linked from the index pages. Acceptance: every doc reachable from `docs/methodology.md` § Document Index.

### I — Thesis sources

Three to integrate:
- FHNW IRF publication (https://irf.fhnw.ch/entities/publication/ce5bf053-9c16-41ac-a212-31eb583f1028)
- FHNW Studierendenprojekt 2481 p. 40-41 (https://studierendenprojekte.wirtschaft.fhnw.ch/view/2481)
- arXiv 2508.18255 (https://arxiv.org/pdf/2508.18255)

**Task #112.**

---

## Suggested order for the defence prep window

This is my recommendation — reorder based on what makes supervisor meetings most productive:

1. **Bug 1, Bug 3** (signal_type cleanup) — one SQL session, immediate quality win on the website
2. **M.1** (semantic dedup turned on) — needed before any per-system numbers are defensible
3. **C.1 / S.4b** (gold-standard human coding) — highest leverage for evaluation; do incrementally
4. **B.1** (Quantum Insider RSS) — 30-min change, weeks of coverage payoff
5. **S.3 / S.4a** (signal judgement page) — feeds C.1 + the learning loop
6. **C.2** (Atlas.ti prompt framing) — small change, big methodology win
7. **I** (thesis sources) — read + cite
8. **D.1** (defense ambivalence research) — read before code
9. **A.1 / S.2** (two-tier auth) — when the site goes wider
10. **F.1, F.2, E.1, B.2, B.3, C.3, C.4, D.2, D.3, G.1, C.2-mobile** — defer

Items get added by Anna at any time. Items never get removed.
