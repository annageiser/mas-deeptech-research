# System A — MASFactory architecture

> This document describes only **System A** (the MASFactory-orchestrated pipeline). System B (Hermes Agent) is documented separately when it lands.

## High-level shape

The architecture exactly mirrors the diagram in the thesis disposition, with one Docker container hosting one MASFactory `RootGraph` on a Hostinger Ubuntu VPS:

```
Hostinger Ubuntu VPS
└── cron (host) ── docker compose run --rm masfactory ──┐
                                                        │
                                  Docker Compose (VPS)  │
                                  └── Container A       │
                                      │ entrypoint.sh   │
                                      │ python -m masfactory_system.runner run-once
                                      ▼
                          ┌────────────────────────────────────────────────┐
                          │  RootGraph "masfactory_swiss_quantum"          │
                          │                                                │
                          │  ENTRY ──► Planner   (Agent)                   │
                          │            │                                   │
                          │            ▼                                   │
                          │         Retriever  (CustomNode)                │
                          │            │                                   │
                          │            ▼                                   │
                          │         Extractor  (Agent)                     │
                          │            │                                   │
                          │            ▼                                   │
                          │         Classifier (Agent) ──┐                 │
                          │            │                 │                 │
                          │            ▼                 ▼                 │
                          │         Critic     (Agent)   │                 │
                          │            │                 │                 │
                          │            ▼                 ▼                 │
                          │         Analyst    (Agent) ──► Persistence ──► EXIT
                          │                              (CustomNode)      │
                          └────────────────────────────────────────────────┘
                                       │              │
                                       ▼              ▼
                              data/raw/runs/   Supabase (Postgres + pgvector)
                              (per-run audit)  actors, signals, runs, token_usage, audit_log
                                       ▲              ▲
                                       │              │
                              OpenRouter API ─── LegacyOpenAIModel (Chat Completions)
                              main:     nvidia/nemotron-3-super-120b-a12b:free
                              fallback: meta-llama/llama-3.3-70b-instruct:free
```

## The seven nodes

Each node has a single responsibility. Five are LLM agents, two are pure Python.

| # | Node | Kind | Reads | Writes |
|---|------|------|-------|--------|
| 1 | Planner    | `Agent`      | `candidate_actors_json`, `limit_actors` | `plan_json` |
| 2 | Retriever  | `CustomNode` | `plan_json`, `actor_pool`               | `documents_json`, `documents_count` |
| 3 | Extractor  | `Agent`      | `documents_json`                        | `candidates_json` |
| 4 | Classifier | `Agent`      | `candidates_json`                       | `classified_json` |
| 5 | Critic     | `Agent`      | `classified_json`                       | `critique_json` |
| 6 | Analyst    | `Agent`      | `plan_json`, `surviving_signals_json`   | `brief_md` |
| 7 | Persistence| `CustomNode` | `classified_json`, `critique_json`, `brief_md`, `store`, `audit_folder`, `run_id` | `signals_kept`, `signals_inserted`, `surviving_signals_json` |

### Why Planner is an Agent (not a CustomNode)

For v1 the Planner could be a hard-coded round-robin. Modelling it as an LLM-driven node from the start means the thesis can evolve the selection logic (prioritise actors with recent signals, balance categories, react to weekly news) without changing the graph wiring. The cost is a few hundred tokens per run — acceptable on the free Nemotron tier.

### Why Retriever and Persistence are CustomNodes

Network IO (arXiv API, website fetches, Supabase writes) has no judgement content — keeping it outside the LLM loop makes token costs predictable and lets us retry the deterministic parts independently.

## Data contracts

Both this system and System B (Hermes) write to the **same Supabase tables**. The schema in [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) is the canonical contract:

- `actors` — primary key `slug`, upserted on every run
- `runs` — one row per `g.invoke()`, with `system in ('masfactory','hermes')`
- `signals` — unique on `(actor_slug, source_url, content_hash)`; carries a `vector(768)` embedding column (populated later by the Critic when we wire embeddings)
- `token_usage` — per-node, per-run; the thesis's cost analysis reads from here
- `audit_log` — raw prompts and outputs, JSONB; complements the per-run audit folder on disk

## Reproducibility surface

For every run, the artefact that survives is the audit folder at `data/raw/runs/<iso-ts>/`:

```
data/raw/runs/2026-05-19T09-12-31Z/
├── config.json              # redacted runtime config
├── actor_pool.json          # the 40-actor list as of this run
├── classifications.json     # raw Classifier output
├── critique.json            # raw Critic output
├── signals.json             # signals kept and written to Supabase
├── brief.md                 # human-readable per-actor brief
└── final_attributes.json    # everything else for postmortem
```

These folders are the citation surface for the thesis: every claim about "what System A found on date X" can be traced back to a specific folder and a specific Supabase row.

## Model choice

Free `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter. 120B parameters with 12B active (MoE), 260k context window — large enough to push the entire actor list and all retrieved documents through the Extractor in one pass. The fallback model is `meta-llama/llama-3.3-70b-instruct:free`, which trips automatically on rate-limit or 5xx.

Both adapters use `LegacyOpenAIModel` (Chat Completions) — required because OpenRouter does not implement OpenAI's Responses API that the newer `OpenAIModel` adapter targets.

## Cron schedule

The host cron drives runs (see [`systems/masfactory/crontab.sample`](../systems/masfactory/crontab.sample) — every 6 hours by default). Each run is a single `docker compose run --rm masfactory run-once` invocation, so a missed cron tick leaves no zombie process and a stuck run is killed by the next tick.
