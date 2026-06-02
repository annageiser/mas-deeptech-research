# Methodology — how the skeleton instantiates the constructive research approach

The thesis follows the **constructive research approach** (Kasanen, Lukka & Siitonen, 1993): build an artefact that addresses a real problem and evaluate how well it does so. This document records the design decisions that turn the disposition's plan into running code.

> **For the substantive signal-theory grounding** — see the dedicated reference at [`docs/signal-taxonomy.md`](signal-taxonomy.md), which documents the **Ehrenthal et al. (2026) four-signal scheme** (`legitimacy` / `customer_cocreation` / `community_ecosystem` / `future_trajectory`), the 19 sub-dimensions, the two explicit extensions, the v0.3.0→v0.4.0 migration table, and the supporting literature (Suchman 1995, Connelly et al. 2011, Spence 1973, Rieger et al. 2025, Knight & Cavusgil 2004, Hilkamo & Granqvist 2022, Tomesh et al. 2022, Adner 2017, Mohr & Sarin 2009, Kolbe & Burnett 1991, Blomqvist et al. 2008, Song et al. 2025, Robinson & Veresiu 2025).
>
> The same content is rendered to the live **Methodology** page at [`https://mas-deeptech-research.cloud/methodology`](https://mas-deeptech-research.cloud/methodology) and the **Signalling theory** page at [`/signalling`](https://mas-deeptech-research.cloud/signalling) — both consume `/api/meta`, which loads [`classification/schema.yaml`](../systems/masfactory/masfactory_system/classification/schema.yaml) verbatim, so the rendered pages and the running agents cite identical sources.
>
> *This* document covers methodology in the narrower software-research sense (Kasanen et al.), not signal theory.

## Two-step validation

| Stage | What the disposition says | Where it lives in this repo |
| --- | --- | --- |
| 1 — Theoretical validation | Derivation of an ideal reference architecture from a systematic literature review. Both candidate implementations are mapped onto this ideal to identify which choices each realises and which it omits. | Tracked in the thesis document; the *gap analysis* will reference specific nodes / loop iterations / skill files in [`docs/architecture.md`](architecture.md). |
| 2 — Empirical validation | Two parallel artefacts run on the same task on the Swiss-quantum ecosystem; cross-system comparison on classification quality, output quality per token cost, reproducibility. | [`systems/masfactory/`](../systems/masfactory) (orchestration-centric graph) and [`systems/hermes/`](../systems/hermes) (memory + skill-centric loop). Shared evaluation in [`evaluation/`](../evaluation). |

## Why System B is built rather than installed

The disposition cites "Hermes Agent (Nous Research, 2025)" as the exemplar of the memory- and skill-centric philosophy. The literal `hermes-agent` CLI from Nous Research **does exist** (open-sourced February 2026, MIT licence, [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com)) — but it is built for *interactive personal assistance*: ~3500 source files, chat gateways for Telegram / Discord / Slack / WhatsApp / Signal / Email / CLI, a Playwright browser, a Node.js TUI, MCP server mode, and a setup wizard that walks a human through configuration.

For a cron-driven batch task that maps an ecosystem on a regular cadence, that interactive shape is the wrong fit. Three concrete reasons:

1. **No clean programmatic entry point.** The Hermes CLI is designed to be driven by chat messages arriving via its gateways. Triggering it from cron would mean simulating an inbound Telegram message — fragile and indirect.
2. **The dependency surface dwarfs the task.** Installing Hermes inside Container B would mean shipping Node.js, npm, Playwright/Chromium, ripgrep, ffmpeg, and a Debian 13 base, for a system whose actual work is a few hundred LLM tokens and an arXiv call.
3. **The comparison would no longer be fair.** System A is ~2,000 lines of focused Python. Embedding the full Hermes runtime in System B would make any cross-system cost / latency comparison meaningless: we'd really be comparing MASFactory + Python vs Hermes-the-platform.

So System B implements the **Hermes pattern** — single long-running AIAgent loop, procedural memory in SQLite, skills as `SKILL.md` files in the agentskills.io format that Hermes uses — without the heavy CLI. The component names in the code (Entry Points, Gateway, AIAgent, Tools Registry, Skills Loader, Memory Manager, Providers, Execution Environments) match the architecture diagram exactly so the thesis-side gap analysis can map them directly.

This is the constructive-research version of "exemplified by Hermes Agent" rather than "powered by Hermes Agent" — which is precisely the language the disposition uses.

## Reproducibility, designed in (not bolted on)

The disposition (§Research Methods → *Constructive development*) commits to having reproducibility infrastructure ready *before* either system is built. What the repo ships against that commitment:

- **Pinned dependencies** — `masfactory==1.0.3`, the OpenAI Python SDK with a `>=` floor, and a fixed Python image (`python:3.11-slim`) for both containers.
- **Versioned prompts and skills** — System A's prompts live inline next to each agent node; System B's skills are `SKILL.md` files. Both move with git; `git log -p` answers "what was the prompt / skill on date X?".
- **Per-run audit trail** — every run creates `data/raw/runs/<iso-ts>__<system>/` containing raw config, classifications, critique, surviving signals, the markdown brief, and the conversation transcript (System B). The directory is bind-mounted from the host so it survives container rebuilds.
- **Per-model token tally** — written to Supabase `token_usage` (one row per node-or-model per run) and to the same audit folder. Primary input for the "output quality per token cost" evaluation.
- **Docker-on-VPS** — the same image runs identically on any Hostinger VPS with the same `.env`. The `RUN ... build-check` step in each Dockerfile means a broken image never reaches the VPS.
- **Shared Supabase schema** — applied once in the Supabase SQL editor, both systems write to the same tables, distinguished by `runs.system`. The comparison cannot be poisoned by schema drift.

## Build–evaluate–refine cycles

Both systems' code surfaces are deliberately small so a single B–E–R cycle is cheap:

1. Edit one prompt (System A) or one `SKILL.md` (System B).
2. `docker compose build <service>` (~1 min; build-check runs).
3. `docker compose run --rm <service> run-once --limit-actors 2` (~2 min).
4. Inspect the new audit folder and the Supabase rows.

Triweekly supervisor reviews should bring at most two prompt/skill changes between reviews — anything larger should escalate to a graph-shape change (System A) or a new tool / memory layer (System B), which is what the architecture-gap analysis is *for*.

## Already shipped (in scope but worth flagging as substantial)

- **Public website — FastAPI + Next.js 14 stack** (Containers F + G, milestone M7+) — live at [`https://mas-deeptech-research.cloud`](https://mas-deeptech-research.cloud). FastAPI JSON service with 11 endpoints over Supabase; Next.js App Router frontend with 11 typed pages: Overview, Signalling theory, Impact leaderboard, Ecosystem, Actors (index + per-actor spotlight), Compare two actors, Knowledge graph (dependency-free SVG, with hover-inspector showing per-edge meaning), Signals, Reports, Methodology. The FastAPI layer serves the canonical `classification/schema.yaml` via `/api/meta`, so the rendered Methodology + Signalling pages cite *exactly* what the agents run.
- **Signalling-theory classification schema v0.4.0** — aligned 1:1 with Ehrenthal et al. (2026)'s four-signal scheme: 4 top-level signal types × 19 sub-categories (17 verbatim from the paper's coded markers + 2 explicit extensions, `funding_event` and `regulatory_recognition`, both flagged `extension: true` and grounded in Suchman 1995 / Rieger et al. 2025). Each sub-category retains the signal_cost (Spence 1973) and observability (Connelly et al. 2011) axes. Operationalises the credibility mechanism via credibility-weighted impact (high-cost signals weighted 1.0, medium 0.7, low 0.4) and the `cheap_talk_ratio` metric. Full taxonomy in [`docs/signal-taxonomy.md`](signal-taxonomy.md).
- **Schema v0.3.0 → v0.4.0 migration** — idempotent SQL block in [`schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) (also paste-ready in [`docs/migrations.md`](migrations.md)) rewrites legacy 9-key `dimension` values to the new 19-key set in place, backfills the new `signal_type` column, and preserves the original value in `dimension_legacy` so pre-migration analyses remain reproducible. No data loss; the Classifier prompt now reasons signal_type → dimension; `labels.py` provides `normalise_dimension()` so any code path receiving a legacy key transparently resolves to the v0.4.0 label.
- **Widened collection funnel + stricter Critic** (v0.4.0) — five collectors per actor (arXiv, actor website, Google News, Bing News press, EPO patents) with limits doubled to 10 each; queries widened from `"<actor>" quantum` to `"<actor>" (quantum OR qubit OR QKD)` to catch quantum subfields; Critic prompt rewritten with explicit DROP RULES (actor-relevance → quantum-relevance → dimension-evidence match → confidence ≥ 0.45 → boilerplate → duplicates), framed as "precision over recall now that the funnel is wider".
- **EPO Open Patent Services patent collector** — fills the schema's reserved `source_kind='swissreg'` (now labelled `patents` under `legitimacy`) via the free EPO OPS 3.2 API. OAuth2 with 18-min cached token; CQL search restricts to quantum IPC classes + title/abstract keyword; covers CH + WO + EP filings naming the actor as applicant. Env-gated by `EPO_OPS_CONSUMER_KEY`+`EPO_OPS_CONSUMER_SECRET`; no keys → silent no-op.
- **pgvector embeddings on `signals.embedding`** — `BAAI/bge-base-en-v1.5` (768d) via fastembed (ONNX, no torch). Off by default; per-system gates `MASF_EMBEDDINGS=1` / `HRM_EMBEDDINGS=1`. Unlocks the `signals_embedding_ivfflat_idx` (auto-created once non-null embeddings appear) and the semantic-dedup layer below.
- **Semantic dedup via pgvector cosine** — Postgres RPC `find_similar_signals(actor, embedding, days, limit)` finds the nearest existing signal for the actor; the Persistence step drops candidates whose nearest neighbour exceeds the configurable threshold (default 0.92 cosine similarity, 30-day window). Per-drop record (matched id, similarity, threshold) logged to `semantic_dedup.json` in the run audit folder.
- **Consensus Critic (Wang et al. 2023)** — `MASF_CRITIC_CONSENSUS_PASSES=3` swaps the single Critic node for 3 independent Critic Agents + a majority-vote CustomNode. Per-pass disagreement recorded for the thesis's inter-pass-agreement analysis.
- **Multi-agent debate Critic (Du et al. 2023)** — `MASF_CRITIC_DEBATE_ROUNDS=1` (requires consensus) inserts 3 debate Agents + 3 snapshot nodes between the consensus snapshots and the vote. Each debate Agent gets a per-agent prompt labelling it "Critic #N" pointing at its own prior verdict so per-agent identity is preserved across rounds. Vote runs over the post-debate verdicts.
- **Per-actor Loop in the System A graph** (was a "deliberate omission" in v1; now shipped) — `PrepareCurrentActor` → Extractor → Classifier → Critic → `AccumulateActor` wrapped in a MASFactory Loop, so each actor's documents are processed in isolation. Persistence also drops hallucinated `(actor_slug, source_url)` pairs to `dropped_hallucinations.json`.
- **Press-release aggregator collector** (third broader-web channel beyond actor websites + Google News). Bing News RSS with a PR-flavoured query (`"<Actor>" quantum (announces OR launches OR partners OR funding OR breakthrough)`). Distinct ranker + source mix from Google News; together they triangulate the press signal channel (Kolbe & Burnett 1991). Lives at [`systems/masfactory/collection/press.py`](../systems/masfactory/masfactory_system/collection/press.py) and mirrored in [`systems/hermes/collectors.py`](../systems/hermes/hermes_system/collectors.py) for comparative-validity equivalence.
- **Embeddings on `signals.embedding` (pgvector 768d)** — `BAAI/bge-base-en-v1.5` via `fastembed` (ONNX, no torch). Off by default; turn on per-system with `MASF_EMBEDDINGS=1` / `HRM_EMBEDDINGS=1`. Unlocks semantic dedup in the Critic and nearest-neighbour search via the auto-created `signals_embedding_ivfflat_idx`. Both systems use the same model + composition logic so cross-system signals about the same event embed to nearby points (required for cross-system semantic dedup).
- **Optional consensus Critic (System A)** — `MASF_CRITIC_CONSENSUS_PASSES=3` swaps the single-pass Critic for three independent Critic Agents + a majority-vote CustomNode (self-consistency, Wang et al. 2023). The audit folder records per-pass disagreement so the thesis can report inter-pass agreement rates as a quality proxy. Triples the Critic's LLM cost when enabled (~20-30% to total tokens), so default is off; the evaluation will A/B with both settings to measure the quality lift.
- **Optional multi-agent debate Critic (System A)** — `MASF_CRITIC_DEBATE_ROUNDS=1` extends the consensus Critic into Du, Li, Torralba, Tenenbaum & Mordatch (2023)'s multi-agent debate: after the three independent passes, three debate Agents each see all three prior verdicts and revise. Each debate agent's prompt labels it as Critic #N and points at its own prior verdict so per-agent identity is preserved across rounds. The vote then runs over the post-debate verdicts. Requires `MASF_CRITIC_CONSENSUS_PASSES=3` as a prerequisite. Doubles consensus Critic cost (6× baseline single-pass).
- **Patent ingestion via EPO OPS** — `systems/masfactory/collection/patents.py` + mirrored Hermes tool. Fills the schema's reserved `source_kind='swissreg'` using the European Patent Office's Open Patent Services API (free tier, free registration). Covers Swiss-national (CH), PCT (WO), and European (EP) patents — strictly broader than swissreg.ch's HTML interface. Per actor CQL query restricts to quantum IPC classes (G06N10, H04L9/0852) or title/abstract keyword. Env-gated (`EPO_OPS_CONSUMER_KEY` + `EPO_OPS_CONSUMER_SECRET`); no creds → silent no-op so the cron baseline is unchanged.
- **Semantic dedup in the Critic via pgvector** — `MASF_SEMANTIC_DEDUP=1` (requires `MASF_EMBEDDINGS=1`). Before insert, each signal's embedding is matched against the corpus (same actor, last `MASF_SEMANTIC_DEDUP_DAYS=30` days) via the `find_similar_signals` Postgres function (cosine distance over the `signals_embedding_ivfflat_idx`). If similarity ≥ `MASF_SEMANTIC_DEDUP_THRESHOLD=0.92`, the candidate is dropped + logged to `semantic_dedup.json` in the run audit folder with the matched signal's id. Catches "same event reported by two aggregators" and "rewritten press release" cases that the exact (actor_slug, source_url, content_hash) constraint misses.
- **Streamlit dashboard** (Container D) — original 9-page stakeholder UI. Demoted to transitional fallback on internal `:8501` after the FastAPI + Next.js cutover; kept until the new site is proven across a full review cycle.
- **Synthesis reports** (Container C) — daily per-system + weekly per-system + weekly thesis-progress markdown reports, rendered on the website's `/reports` page.
- **Per-system signal column** (`signals.system`) — denormalised + backfilled so cross-system queries don't have to join on `runs`.
- **Hand-editable actors** — Supabase Table editor can edit `arxiv_query` and `notes` without next run overwriting them.

## Deliberate omissions in v1

The disposition's evaluation depends on the *gap* between the ideal architecture and what's built. These omissions are intentional in v1 so the gap analysis has honest material:

- **Telegram gateway on System B** (`TelegramGatewayStub` exists with a no-op body). Flip-the-switch addition once cron-driven evaluation is complete.
- **R≥2 debate rounds on the multi-agent debate Critic** — only R=1 implemented; Du et al. (2023) Figure 4 shows plateauing gains past one round for classification-style tasks, but the assumption is worth empirically validating if the evaluation has spare LLM budget.
- **Authentication on the public site** — currently anyone can hit any route. Acceptable for a read-only research dashboard with public-domain data, but worth flagging.
- **Retire the legacy Streamlit dashboard** (Container D) once the new Next.js site is proven across a full review cycle.

## Document index

The thesis-feeding documentation, in order of typical relevance:

| Doc | What it covers |
|---|---|
| [`architecture.md`](architecture.md) | Container topology, mermaid diagram, per-system node table, five-collector funnel, optional capability layers, audit-trail file listing |
| [`signal-taxonomy.md`](signal-taxonomy.md) | Thesis-citable reference for Ehrenthal's four-signal scheme + our 19 sub-categories + extensions + literature |
| [`reproducibility.md`](reproducibility.md) | Hostinger VPS runbook + env-var reference for all optional capability layers |
| [`migrations.md`](migrations.md) | Paste-ready SQL blocks for each Supabase schema change since initial deploy (all idempotent) |
| [`session_log.md`](session_log.md) | Chronological assistant-side build journal with token costs per session |
| [`dns-and-dashboard.md`](dns-and-dashboard.md) | DNS + Caddy setup for the public domain |
| [`ssh-go-live.md`](ssh-go-live.md) | Original SSH-assisted go-live walkthrough |
