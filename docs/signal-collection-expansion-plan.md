# Plan — expand signal collection beyond the current 5 sources

The current funnel pulls from **arXiv · actor website · Google News · Bing News (press) · EPO patents** (last is env-gated). This plan catalogues 14 candidate new sources, prioritises them by **(yield × ease) ÷ legal risk**, and maps each one to the Ehrenthal sub-category it would best populate.

Goal: every one of the 19 v0.4.0 sub-categories should have at least one collector pointing at it. Today's gaps:

| Sub-category | Current collector | Status |
|---|---|---|
| `leadership_expertise` | website + news | OK |
| `patents` | EPO OPS | OK (env-gated) |
| `publications` | arXiv (with author-affiliation fix in v0.4.1) | OK |
| `awards` | news only | **under-sampled** |
| `testimonials` | website only | **under-sampled** |
| `educational_outreach` | website only | **under-sampled** |
| `funding_event` | news + press | OK |
| `regulatory_recognition` | news only | **under-sampled** |
| `collaborations_applications` | press + news | OK |
| `pilots_pocs` | press + news | OK |
| `customer_training` | website | **under-sampled** |
| `cloud_platform_listings` | (none) | **MISSING** |
| `hpc_collaborations` | news only | **under-sampled** |
| `industry_partnerships` | press | OK |
| `academic_partnerships` | website + news | OK |
| `roadmaps` | website | OK |
| `milestones` | website + news | OK |
| `technological_advances` | arXiv + website | OK |
| `long_horizon_claims` | website + roadmap pages | OK |

The plan below adds **6 new collectors** that close those gaps and **broadens 3 existing collectors** to deepen coverage.

---

## Priority 1 — close the `cloud_platform_listings` gap (zero today)

This is Ehrenthal's **single highest-frequency sub-category** (43% of all community-ecosystem signals in the paper's vendor corpus). We capture none of it. Highest-impact fix.

### 1.1 — Cloud-quantum-platform directory scraper (NEW)

| Spec | Value |
|---|---|
| What | Scrape the public directories of AWS Braket / Azure Quantum / IBM Quantum Network / Google Quantum AI / OQC Cloud for hardware-provider listings + customer success stories |
| Yield | ~5-15 signals per platform refresh; perfect fit for `cloud_platform_listings` + `testimonials` |
| Tech | Static HTML where possible; OPS-style JSON endpoint where one exists. `httpx` + `selectolax` — already in deps |
| Legal | All five publish vendor directories as marketing material; ToS allow reading for non-commercial research. Note in audit log + cap to 1 req / 3s |
| Dev cost | ~half-day per platform, ~2 days total |
| Priority | **HIGHEST — closes the missing-collector gap on the most-frequent sub-category** |

Implementation: `systems/masfactory/collection/cloud_platforms.py`. Mirror in Hermes as a `cloud_platform_search` tool. Each refresh produces zero or more Documents per actor whose actor.name appears in any platform's vendor list.

---

## Priority 2 — close the `awards` + `regulatory_recognition` gaps

Both are Ehrenthal high-frequency markers (awards 19% of legitimacy; regulatory is our Swiss-context extension) that are currently leaking through generic news search instead of being directly sampled.

### 2.1 — Swiss federal-strategy + funding-body scraper (NEW)

| Spec | Value |
|---|---|
| What | Targeted scrape of (a) [SBFI federal-strategy publications](https://www.sbfi.admin.ch/sbfi/en/home.html), (b) [SNF awarded-grants database](https://data.snf.ch/grants), (c) [Innosuisse project repository](https://www.innosuisse.admin.ch/inno/en/home/find-out-about-innosuisse/projects.html). Each has a search interface or CSV download — no scraping anti-bot. |
| Yield | The single highest-signal Swiss-specific source. Catches every federally-awarded grant + every federal-strategy mention by name. |
| Tech | SNF has a documented JSON API at `data.snf.ch/api`. Innosuisse + SBFI are HTML. |
| Legal | All three are federal-government public data, explicitly licensed for re-use. |
| Dev cost | ~1 day total (3 sub-collectors) |
| Priority | **HIGH — Swiss-specific, fills two sub-categories, government-data licensed** |

Populates: `funding_event` (SNF grants) + `regulatory_recognition` (SBFI / strategy) + `educational_outreach` (Innosuisse training programmes).

### 2.2 — Conference & awards aggregator (NEW)

| Spec | Value |
|---|---|
| What | Pull the awards / programme lists from IEEE Quantum Week, APS March Meeting (focus sessions), Q2B, Quantum.Tech, and ETH-Zurich Quantum Day. Each publishes a public attendee / award page. |
| Yield | ~5-20 signals per conference cycle (~quarterly per source) for `awards` |
| Tech | HTML scrape; some have RSS / iCal exports |
| Legal | Public conference pages — fine |
| Dev cost | ~1 day |
| Priority | **MEDIUM — fills the awards gap** |

---

## Priority 3 — broaden patent coverage

EPO OPS (env-gated) is our only patent source today and depends on registration. Two complementary additions widen patent yield without changing the env gate.

### 3.1 — USPTO PatentsView API (NEW)

| Spec | Value |
|---|---|
| What | The official USPTO open data API. Free, no registration, JSON. Search by applicant / inventor / classification. Catches US patents naming Swiss applicants — a category EPO OPS only partially covers. |
| Yield | ~3-8 signals per actor per year (Swiss quantum has a US-filing tail) |
| Tech | `https://search.patentsview.org/api/v1/patent/` — POST with JSON query |
| Legal | US-government open data, fully unrestricted |
| Dev cost | ~half-day |
| Priority | **MEDIUM** |

### 3.2 — Google Patents XHR endpoint (NEW, fallback when EPO OPS unconfigured)

| Spec | Value |
|---|---|
| What | The undocumented but widely-used `https://patents.google.com/xhr/query?url=...` endpoint returns JSON for any search query. Acts as the patent collector for deployments without EPO OPS credentials. |
| Yield | Similar to EPO OPS but with less reliable affiliation matching |
| Tech | `httpx` + JSON parsing |
| Legal | Undocumented endpoint; Google may rate-limit or change without notice. Cap to 1 req / 5s + cache aggressively |
| Dev cost | ~half-day |
| Priority | **MEDIUM — graceful degradation when EPO OPS isn't configured** |

---

## Priority 4 — academic publications beyond arXiv

### 4.1 — Crossref / OpenAlex (NEW)

| Spec | Value |
|---|---|
| What | [Crossref API](https://api.crossref.org) for DOI-indexed papers (journals + proceedings, much broader than arXiv); [OpenAlex API](https://api.openalex.org) for the same data with normalised affiliations |
| Yield | OpenAlex is the clear winner — it has cleaned affiliation IDs (e.g. ROR ID for ETH Zurich) so the author-affiliation match becomes deterministic instead of substring-matching free-text |
| Tech | OpenAlex: `https://api.openalex.org/works?filter=institutions.id:I35440088` (the ETH Zurich ROR ID) — pure JSON, no auth, polite pool with email param |
| Legal | OpenAlex is CC0 (public domain) |
| Dev cost | ~1 day (replace arXiv as primary; keep arXiv as supplemental) |
| Priority | **HIGH — strictly better than arXiv for affiliation-attribution accuracy** |

The author-affiliation bug fix in v0.4.1 still works against fuzzy strings, but OpenAlex's normalised institution IDs eliminate that whole class of bug.

---

## Priority 5 — software / GitHub signals

Quantum vendors increasingly ship open-source toolchains (Qiskit / Cirq / PennyLane / IBM Composer). These are observable `technological_advances` + `customer_training` signals.

### 5.1 — GitHub Releases + GitHub Discussions (NEW)

| Spec | Value |
|---|---|
| What | For each actor with a public GitHub org (configurable in `actors.yaml`), pull releases (new versions = `technological_advances` / `milestones`) + Discussions posts (`customer_training` / `educational_outreach`) |
| Yield | High for the ~6-8 actors with public repos (ETH Zurich's quantumlib, EPFL's QML libraries, ID Quantique's SDK, IBM Quantum Network); zero for the others |
| Tech | GitHub REST API; PAT for higher rate limit (env-gated, optional) |
| Legal | Public-repo metadata is licensed under each repo's terms; usage falls under GitHub's API terms |
| Dev cost | ~half-day |
| Priority | **MEDIUM — narrow but rich source for the actors who use GitHub** |

---

## Priority 6 — broader news + social

### 6.1 — Swiss media direct feeds (NEW)

| Spec | Value |
|---|---|
| What | RSS feeds from NZZ, Le Temps, SwissInfo, Watson — Swiss-domestic news that Google News under-samples |
| Yield | ~2-5 signals / week / outlet for Swiss-domestic quantum coverage |
| Tech | Standard RSS via existing `feedparser`; just a curated URL list per outlet |
| Legal | RSS is explicitly publish-to-aggregator content |
| Dev cost | ~half-day |
| Priority | **LOW (rolling improvement on existing coverage)** |

### 6.2 — Mastodon / Bluesky (NEW)

| Spec | Value |
|---|---|
| What | Twitter died for serious research; both platforms have open APIs. Pull posts from actor accounts + posts tagged #quantum + #Switzerland |
| Yield | Variable; some Swiss-quantum researchers post substantively, most do not |
| Tech | Mastodon `/api/v1/timelines/tag/{tag}`; Bluesky's AT Protocol |
| Legal | Both fully open |
| Dev cost | ~half-day |
| Priority | **LOW** |

### 6.3 — LinkedIn — **NOT RECOMMENDED**

LinkedIn aggressively blocks scraping (IP blocks, account bans, ToS forbids). Legitimate access requires LinkedIn Marketing Partner status (B2B sales partnership, expensive, slow). The only ethical path is the third-party data brokers (Apollo, ZoomInfo, Crunchbase) — paid, expensive, and they get their data through similar grey-area methods.

**Recommendation:** explicitly mark LinkedIn as out-of-scope in the thesis and document why. The thesis's chapter 4.1.4 (Methodological Limitations) cites this as an example of a high-yield source whose acquisition cost exceeds a BSc-thesis budget.

---

## Priority 7 — events + jobs (broader-web)

### 7.1 — jobs.ch quantum-keyword feed (NEW)

| Spec | Value |
|---|---|
| What | Job postings mentioning quantum from Swiss actors — direct signal of `leadership_expertise` + `educational_outreach` + hiring momentum |
| Yield | ~5-15 postings / week ecosystem-wide |
| Tech | jobs.ch has a partner API (free for non-commercial use); fallback HTML scrape |
| Legal | jobs.ch ToS allows non-commercial research scraping |
| Dev cost | ~half-day |
| Priority | **LOW-MEDIUM** |

---

## Summary table (sorted by priority)

| # | Collector | Fills | Yield | Dev cost | Priority |
|---|---|---|---|---|---|
| 1.1 | Cloud-quantum platforms | `cloud_platform_listings` (currently zero) + `testimonials` | 5-15 / refresh | 2 d | **HIGHEST** |
| 2.1 | Swiss federal scraper (SBFI + SNF + Innosuisse) | `funding_event` + `regulatory_recognition` + `educational_outreach` | very high (Swiss-only) | 1 d | HIGH |
| 4.1 | OpenAlex API | `publications` (replacing arXiv for affiliation precision) | strictly better than arXiv | 1 d | HIGH |
| 3.1 | USPTO PatentsView | `patents` (US-filed) | 3-8 / actor / yr | half-day | MED |
| 3.2 | Google Patents fallback | `patents` (when EPO unconfigured) | similar to EPO | half-day | MED |
| 5.1 | GitHub Releases | `technological_advances` + `customer_training` | high for ~6 actors | half-day | MED |
| 2.2 | Conference awards aggregator | `awards` | 5-20 / cycle | 1 d | MED |
| 6.1 | Swiss media direct feeds | better `awards` / `industry_partnerships` | 2-5 / wk / outlet | half-day | LOW |
| 7.1 | jobs.ch | `leadership_expertise` (hiring momentum) | 5-15 / wk | half-day | LOW-MED |
| 6.2 | Mastodon / Bluesky | various | variable | half-day | LOW |
| 6.3 | LinkedIn | various | high | impossible legally | **NOT RECOMMENDED** |

**Total dev cost** for all green-light items (1.1 + 2.1 + 4.1 + 3.1 + 3.2 + 5.1 + 2.2): **~7 days of focused implementation.** Each is a self-contained module mirroring the existing `collection/*.py` pattern; each adds an entry to the per-actor collector matrix in `retriever.py`.

---

## Recommended sequencing

| Week | Items | Outcome |
|---|---|---|
| Week 1 | 1.1 (cloud platforms) + 2.1 (Swiss federal) | The two biggest gaps closed; full Ehrenthal scheme is now sampled |
| Week 2 | 4.1 (OpenAlex) + 5.1 (GitHub) | Publications-attribution becomes ID-based; software signals captured |
| Week 3 | 3.1 + 3.2 (patent fallbacks) + 2.2 (conferences) | Patents work without EPO creds; awards directly sampled |
| Week 4 | 6.1 + 7.1 (jobs/Swiss media) — discretionary | Round-out coverage if budget remains |

Each collector follows the same self-contained pattern as the existing five: a new module in `systems/masfactory/collection/`, a mirror tool in `systems/hermes/collectors.py`, two registration lines in `retriever.py`, env-gated where the source needs credentials.

---

## Cross-cutting fix (v0.4.1, already shipped)

**Author-affiliation gate on arXiv.** The original bug Anna reported (a publication signal where the actor wasn't actually the author) is fixed in commit `<this commit>`: the arXiv collector now reads each entry's `<arxiv:affiliation>` tag and drops papers where no author's affiliation matches the actor's `name` or its `aliases`. Per-actor `aliases` field added to the Actor schema (`schema.py`). Both systems benefit. Critic prompt strengthened with a publications-specific DROP RULE that demands authorship evidence (not mere mention) in the evidence_quote.

This fix is independent of the new collectors above — it tightens the existing arXiv collector, and the same `_belongs_to_actor` pattern can be reused by 1.1 (cloud platforms) and 5.1 (GitHub) where actor attribution is similarly fuzzy.

---

## Thesis framing

The thesis can cite this expansion plan in:

- **Chapter 3.5.2** (Results — coverage) — report the gap-filling progression: "v0.4.0 sampled 14/19 sub-categories; the v0.4.1+ expansion closes the remaining 5 gaps including the highest-frequency one (cloud_platform_listings)."
- **Chapter 4.1.2** (Comparative Evaluation) — the gap analysis can use this plan as the structured rubric for "what an ideal architecture would also do."
- **Chapter 5.3** (Future Research Directions) — the LOW-priority items + LinkedIn discussion are natural follow-on work for a future researcher.
