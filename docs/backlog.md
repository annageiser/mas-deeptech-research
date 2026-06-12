# Backlog — thesis-scope features and methodology work

Discrete to-dos that are **scoped but not yet done**. Each has an explicit acceptance check so we know when it's finished. Sorted by category, not priority.

This is the strategic backlog. For tool/library evaluation see [`feature-candidates.md`](feature-candidates.md). For session-by-session iteration log see [`iterations/`](iterations/).

---

## A — Authentication & access control

### A.1 — Two user groups on the public site (admin + user)

Currently the Caddy basic-auth gate is a single role (`anna`, full access). Split into:
- **admin** (`anna`) — full read/write incl. flagging, validating, future stock-validator etc.
- **user** — read-only access to all pages.

**Implementation sketch:**
- `caddy/Caddyfile` keeps `basicauth` for the user role
- Admin-only routes (`/api/signal-flags`, future `/api/validate`, etc.) get a second `basicauth` block matching only admin credentials
- OR migrate to a tiny FastAPI middleware on the API layer that reads role from a header

**Acceptance:** non-admin user can read every page but cannot POST to any state-mutating endpoint; the `/signals` page hides the "Report wrong" button for non-admins.

---

## B — Coverage expansion (RSS-based, token-efficient)

### B.1 — Subscribe to quality industry blogs as signal sources

Blogs are token-efficient because they emit RSS — we already process the feed metadata and only LLM-classify titles + abstracts. Cost per signal ~1/10 of full-page web search.

**Vetted blogs to add now:**
- **The Quantum Insider — daily feed** (https://thequantuminsider.com/category/daily/) — seriös, established, daily cadence
- *More candidates to be discovered via Hermes's blog-watcher skill (see B.2)*

**Implementation sketch:**
- Add to `data/raw/rss_feeds.yaml` under a new `industry_blogs:` section
- MASFactory's existing `collection/rss.py` handles it automatically
- For Hermes, the bundled `blogwatcher` skill picks up RSS feeds (we already saw it in the 75-skill list from the upstream image)

**Acceptance:** the daily cron produces ≥5 signals/week from `source_kind='blog'` or matched against `thequantuminsider.com`.

### B.2 — Use Hermes's bundled `blogwatcher` skill

Already installed in the upstream image but not loaded by our cron run. Load it alongside our `collect-swiss-quantum-signals` skill and let the agent monitor any RSS feeds it discovers.

**Implementation sketch:**
- `--skills collect-swiss-quantum-signals,arxiv,blogwatcher` in `collect_all_actors.sh`
- Update skill instructions to say "use the bundled `blogwatcher` skill when you discover an RSS feed"
- Document signal-quality criteria so the agent only ingests serious sources (Quantum Insider yes, random Substack maybe-not)

**Acceptance:** at least one cron run produces blogwatcher-attributed signals with a verifiable RSS source.

### B.3 — Coverage measurement: "how much is each system actually processing?"

Define a coverage metric: signals/actor/week, by source_kind. Add a column to `/api/coverage` and a per-system bar chart on `/compare`.

**Acceptance:** dashboard chart showing signals-per-actor-per-week per system per source_kind for the trailing 30 days.

---

## C — Methodology framing (LLM prompts + human comparison)

### C.1 — Human-in-the-loop parallel coding (you do what the systems do)

Anna manually finds + classifies signals for a sub-sample of actors using the same Ehrenthal scheme. This becomes the **gold-standard** for evaluation: did the systems find what a human researcher would?

**Implementation sketch:**
- Pick ~5 actors as the gold subset (mix of categories)
- Anna uses the `signal_flags` table + a new `human_validated=true` marker (already in schema since v0.4.2)
- Each manually-collected signal gets `inserted_by='anna'` and is excluded from system-vs-system comparisons (counted as ground truth instead)
- Quality metric becomes: precision-against-Anna and recall-against-Anna per system

**Acceptance:** 50+ gold signals from Anna across 5 actors; `/api/evaluate/gold-precision` and `/api/evaluate/gold-recall` endpoints; bar chart in evaluation report.

### C.2 — Tell the LLM the task is normally done by humans with Atlas.ti

Both systems' Classifier/Critic prompts should explicitly frame the task as **"you are doing the qualitative-coding job that a researcher would normally do with [Atlas.ti](https://atlasti.com/de)"**. This is a prompt-engineering decision documented in the methodology.

**Implementation sketch:**
- Update prompts in `systems/masfactory/.../agents/{classifier,critic}.py` and `systems/hermes/skills/.../SKILL.md`
- Add a section to `docs/methodology.md` § "Prompt framing" explaining why
- Versionable: bump `prompt_version` in audit_log so before/after analysis is possible

**Acceptance:** new prompt_version tag in audit_log; methodology.md updated; at least one A/B comparison run.

### C.3 — Project goal statement: "spezifiziere möglichst wenig, krieg möglichst viel heraus"

Currently implicit. Make it explicit in `docs/methodology.md` (introduction) and in the public `/methodology` page. This is the constructive-research framing in plain language.

**Acceptance:** statement appears on the public methodology page + in the abstract of the thesis intro.

---

## D — Defense signals (the ambivalence marker)

### D.1 — Research the defense-ambivalence phenomenon

Companies (especially US-based) increasingly withhold product/progress info citing "national security." This may be genuine or may be a marketing pretext. It's a noncommensurable signal in its own right.

**Examples to research:**
- **D-Wave**: deep US defense ties; quantum-annealing pitched both commercially and to DARPA
- **Anthropic Mythos** (TBC): Anthropic's defense-adjacent positioning
- (Find more US/CH examples for the thesis)

**Open questions for the section:**
1. How does a potential **end-user** decode defense signals?
2. How does a **company that wants to make money** decode them?
3. Can a researcher / outside observer **decipher** what's withheld vs what's genuinely classified?

**Acceptance:** 2-3 page section in `docs/signal-taxonomy.md` § "Defense signals" with worked examples and citations; included in the thesis defence write-up.

### D.2 — Treat "info withheld due to national security" as a **marker**, not a signal

A marker is metadata on the actor record ("this actor exhibits ambivalence around defense disclosure"). Different from a signal (which is a discrete event). Tagged on the `actors` table, queryable per actor.

**Implementation sketch:**
- New column: `actors.defense_ambivalence_marker boolean default false`
- Manual seed for known cases (D-Wave, etc.)
- Display on the actor spotlight page

**Acceptance:** marker column + UI; documented criterion for setting it.

### D.3 — Defense-ambivalence filter on signal collection

When a signal explicitly mentions "national security", "classified", "ITAR", "EAR" — flag it via a new filter that tags the signal as `dimension='defense_ambivalence'`. Different from `defense_engagement` (active defense partnership).

**Acceptance:** filter in `systems/masfactory/.../collection/news.py` matches the keyword set; signals tagged correctly; both Ehrenthal `defense_signals` sub-dimensions populated.

---

## E — Learning loop & self-improvement

### E.1 — "See why you didn't catch them, learn from it"

When Anna's gold-standard flagging surfaces a missed signal (see C.1), the system should:
1. Surface the missed signal in `missed_signals` table (already exists since v0.4.2)
2. Diagnostic: why did the Critic drop it? was it not searched at all? did the Extractor miss it?
3. Feed back into the next prompt iteration

**Implementation sketch:**
- Per-missed-signal: replay the same prompt with the agent + see what it does
- Diagnostic categories: not-searched / extracted-but-dropped / extracted-but-misclassified
- Aggregate into per-actor / per-source-kind miss-rate
- Update the `Classifier` prompt to include 1-shot examples from missed signals (few-shot learning)

**Acceptance:** weekly report includes "Top 5 missed signals from gold set" + diagnostic category for each.

---

## F — Stakeholder actionability

### F.1 — Stakeholder personas: what can each one do with the systems?

Currently the site is a research artefact. Make it actionable per persona:
- **Investor**: "show me signals about funding rounds, leadership hires, M&A in the last quarter"
- **Researcher**: "show me publications + community-ecosystem signals for actors I follow"
- **Enthusiast**: "show me daily quantum-insider digest filtered to Swiss actors"
- **Supervisor/Evaluator**: "show me the gold-precision/recall metrics + methodology"

**Implementation sketch:**
- New page `/personas` with 4 toggles → each loads a pre-filtered view of existing data
- No new data model; just saved-filter URLs

**Acceptance:** four working persona views; each linkable.

### F.2 — Stock validator integration

The disposition mentioned a stock-validator: given an actor signal, check whether the public-equity reaction (if listed) corroborates the signal. We DEFERRED this earlier (task #86) pending supervisor clarification.

**Implementation sketch:**
- Free Yahoo Finance API (or `yfinance` Python package) for listed actors (D-Wave, Quantinuum-parent Honeywell, IonQ etc.)
- Compare signal date ± window to abnormal returns
- Display per-signal on the spotlight page

**Acceptance:** for ≥3 listed actors, the spotlight page shows "stock reaction" badge per signal.

---

## G — GitHub feature research (ongoing)

### G.1 — Audit GitHub for additional tooling to improve the systems

Continuous discovery. Examples to evaluate:
- **[QualCoder](https://github.com/ccbogel/qualcoder)** — qualitative coding for text/image/audio/video, cross-platform. Could inform the Atlas.ti-replacement angle of the LLM prompt framing.
- *(add more as found)*

**Acceptance:** evaluations land in [`docs/feature-candidates.md`](feature-candidates.md) (accepted/rejected with reason).

---

## H — Iteration documentation

### H.1 — Continue iteration docs (each meaningful change → new doc)

Current iteration docs in `docs/iterations/` go through v0.4.18. New format expected for v0.4.19+. The discipline of one-doc-per-change has paid off massively in the Phase B cascade — keep it.

**Acceptance:** every commit with a `v0.4.x:` prefix has a matching `docs/iterations/v0.4.x-*.md` file.

---

## I — Thesis sources to integrate

Papers and projects to cite or extend in the thesis:

| Source | Where to cite |
|---|---|
| [FHNW IRF publication](https://irf.fhnw.ch/entities/publication/ce5bf053-9c16-41ac-a212-31eb583f1028) | Probably Chapter 2 literature review |
| [FHNW Studierendenprojekt 2481 (p. 40-41)](https://studierendenprojekte.wirtschaft.fhnw.ch/view/2481) | Methodology — qualitative coding precedent at FHNW |
| [arXiv 2508.18255](https://arxiv.org/pdf/2508.18255) | Multi-agent comparison literature (TBC after reading) |

**Acceptance:** each appears in the thesis bibliography + at least one in-text citation.

---

## Prioritization

For the **defence preparation window (next 4-6 weeks)**, I'd suggest this rough order:

1. **C.1 (gold-standard human coding)** — highest leverage for evaluation chapter; you can do this incrementally while cron accumulates signals
2. **B.1 (Quantum Insider RSS)** — 30-minute change with weeks of coverage payoff
3. **C.2 (Atlas.ti prompt framing)** — small prompt change, big methodology framing benefit
4. **I (thesis sources)** — read + cite (not coding work)
5. **D.1 (defense-ambivalence research)** — research before code
6. **A.1 (two-role auth)** — only needed when site goes wider
7. **B.3, C.3, D.2, D.3, E.1, F.1, F.2, G.1** — defer until 1-6 progress

This is my recommendation, not a constraint — reorder based on what makes the supervisor meetings most productive.
