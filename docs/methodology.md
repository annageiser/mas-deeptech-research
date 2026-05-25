# Methodology — how the skeleton instantiates the constructive research approach

The thesis follows the **constructive research approach** (Kasanen, Lukka & Siitonen, 1993): build an artefact that addresses a real problem and evaluate how well it does so. This document records the design decisions that turn the disposition's plan into running code.

> **For the substantive signal-theory grounding** — why we measure what we measure, how every score is computed, full per-dimension citations to Ehrenthal et al. (2026), Suchman (1995), Knight & Cavusgil (2004), Hilkamo & Granqvist (2022), Adner (2017), Rieger et al. (2025), Robinson & Veresiu (2025), Song et al. (2025), Tomesh et al. (2022), Mohr & Sarin (2009) — see the live **Methodology** page on the dashboard at `https://mas-deeptech-research.cloud` (or its source at [`systems/dashboard/dashboard_app/pages/9_Methodology.py`](../systems/dashboard/dashboard_app/pages/9_Methodology.py)). The per-dimension literature grounding is also embedded directly in [`systems/masfactory/masfactory_system/classification/schema.yaml`](../systems/masfactory/masfactory_system/classification/schema.yaml) as a `grounding:` field on every dimension.
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

- **Streamlit dashboard** (Container D, milestone M7) — live at `https://mas-deeptech-research.cloud`. 9 pages, scoring + labels modules, full Methodology page with literature grounding.
- **Synthesis reports** (Container C) — daily per-system + weekly per-system + weekly thesis-progress markdown reports.
- **Per-system signal column** (`signals.system`) — denormalised + backfilled so cross-system queries don't have to join on `runs`.
- **Hand-editable actors** — Supabase Table editor can edit `arxiv_query` and `notes` without next run overwriting them.

## Deliberate omissions in v1

The disposition's evaluation depends on the *gap* between the ideal architecture and what's built. These omissions are intentional in v1 so the gap analysis has honest material:

- **Embeddings on `signals.embedding`** (pgvector column exists but is unused). Adding a SentenceTransformer-based embedder in either system is a one-file change.
- **Swissreg patent ingestion**. Schema reserves `source_kind='swissreg'`; both systems would need a new collector.
- **Broader-web signal scraping** — Google News, arXiv-affiliation search, press-release aggregator. Academically supported by Kolbe & Burnett (1991) on content-analysis methodology; deferred to a focused follow-up session.
- **Telegram gateway on System B** (`TelegramGatewayStub` exists with a no-op body). Flip-the-switch addition.
- **Per-actor processing Loop in the System A graph** — Extractor currently sees all actors' documents in one prompt, which is the root cause of the residual attribution challenge. Per-actor Loop (the pattern MASFactory uses in its NowWhat reference app) would isolate each actor's documents.
- **Loop-based "discuss until consensus" critic** on System A. Architecture diagram does not include such a loop; literature review may justify adding one.
