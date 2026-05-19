# Architecture — both systems

> Two systems, one task, one Supabase. The whole point of the comparative design is that signals produced by either system are stored in the same tables and the same audit folder convention, distinguishable only by `runs.system in ('masfactory','hermes')` and the suffix on the audit folder name.

## High-level shape

```
Hostinger Ubuntu VPS
└── host cron ──> docker compose run --rm <service>
                  │
                  ▼
        Docker Compose (VPS)
        ├── Container A — masfactory  (System A)
        │     RootGraph "masfactory_swiss_quantum"
        │     Planner → Retriever → Extractor → Classifier
        │              → Critic → Analyst → Persistence
        │
        └── Container B — hermes      (System B)
              Single AIAgent loop with
              Entry Points + Gateway, Tools Registry,
              Skills Loader, Memory Manager, Providers,
              Execution Environments

         Both write to:                Both call:
            Supabase                     OpenRouter API
            (actors, signals,            ├── nvidia/nemotron-3-super-120b-a12b:free  (main)
             runs, token_usage,          └── meta-llama/llama-3.3-70b-instruct:free  (fallback)
             audit_log;
             pgvector enabled)

         Per-run audit folders on the host's bind-mounted ./data:
            data/raw/runs/<iso-ts>__masfactory/
            data/raw/runs/<iso-ts>__hermes/
```

---

## System A — MASFactory (orchestration-centric graph)

Mirrors the architecture diagram exactly. Linear pipeline:

| # | Node | Kind | Reads | Writes |
|---|------|------|-------|--------|
| 1 | Planner    | `Agent`      | `candidate_actors_json`, `limit_actors` | `plan_json` |
| 2 | Retriever  | `CustomNode` | `plan_json`, `actor_pool`               | `documents_json`, `documents_count` |
| 3 | Extractor  | `Agent`      | `documents_json`                        | `candidates_json` |
| 4 | Classifier | `Agent`      | `candidates_json`                       | `classified_json` |
| 5 | Critic     | `Agent`      | `classified_json`                       | `critique_json` |
| 6 | Analyst    | `Agent`      | `plan_json`, `surviving_signals_json`   | `brief_md` |
| 7 | Persistence| `CustomNode` | `classified_json`, `critique_json`, `brief_md`, `store`, `audit_folder`, `run_id` | `signals_kept`, `signals_inserted`, `surviving_signals_json` |

Code: [`systems/masfactory/masfactory_system/graph.py`](../systems/masfactory/masfactory_system/graph.py).

**Why MASFactory:** the disposition's first architectural strand — multi-agent orchestration as a directed graph of specialised nodes (Liu et al., 2026). Each node is an isolated unit with a single responsibility and a typed contract on its input/output.

**Why the planner is an LLM agent (not Python):** even though for v1 it's mostly mechanical actor selection, modelling it as an agent now means the thesis can evolve it (priority by recent-signal volume, category balancing, news-driven triggers) without rewriting the graph.

---

## System B — Hermes-pattern (memory- and skill-centric loop)

Mirrors the diagram's component box exactly:

| Diagram label | Implementation |
| --- | --- |
| Entry Points + Gateway | `systems/hermes/hermes_system/entry_points/` + `runner.py` (CLI). Telegram is a `TelegramGatewayStub` — wiring exists, body is a no-op. |
| AIAgent (Core Loop) | `systems/hermes/hermes_system/agent/core_loop.py` |
| Tools Registry | `systems/hermes/hermes_system/tools_registry/registry.py` |
| Skills Loader | `systems/hermes/hermes_system/skills_loader/loader.py` |
| Memory Manager | `systems/hermes/hermes_system/memory/sqlite_manager.py` (SQLite) |
| Providers (Model API) | `systems/hermes/hermes_system/providers/openrouter.py` (OpenAI SDK → OpenRouter) |
| Skills | `systems/hermes/skills/{arxiv,scrapling,parallel-cli,research-paper-writing}/SKILL.md` |
| Execution Environments | this Docker container; the SSH execution environment from the diagram is out of scope for v1 |

The core loop is intentionally a single LLM call sequence per actor:

```
for actor in actor_pool[:limit_actors]:
    while iterations < HRM_MAX_ITERATIONS:
        reply = provider.chat(messages)                       # OpenRouter call
        step  = parse_json(reply)                             # {action, tool, args} or {action: finish, summary_md}
        if step.action == "finish": break
        output = tools_registry.call(step.tool, step.args)
        messages.append(tool_result_as_user_message(output))
    memory.record_procedure(actor.slug, brief, sources, dims) # procedural memory write
    supabase.insert_signals(rows)
```

**Why Hermes-pattern (not the literal `hermes-agent` PyPI package):** Nous Research's Hermes Agent is a heavy interactive personal-assistant framework (~3500 files, chat gateways for Telegram/Discord/...). For a cron-driven batch task its interactive flow is the wrong shape, and importing it would also make the System A vs System B comparison unfair (different operational shapes). This system implements the *philosophy* — single long-running agent, procedural memory, skill files — without the gateway machinery. See [`docs/methodology.md`](methodology.md) for the rationale.

---

## Shared data contracts

Both systems write to the same Supabase tables via different client implementations. The canonical schema is [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) (apply once in the Supabase SQL editor).

| Table | Both systems write | Notes |
|---|---|---|
| `actors` | yes (upsert on `slug`) | Either system can refresh the row. |
| `runs` | yes | `system in ('masfactory','hermes')`. One row per `g.invoke()` / per `run_once`. |
| `signals` | yes (idempotent on `actor_slug,source_url,content_hash`) | Same dimensions, same source kinds. |
| `token_usage` | yes | System A logs per node; System B logs per model under `node_name='ai_agent'`. |
| `audit_log` | yes | Free-form JSON appended per node/event. |

Per-run **on-disk** audit folders live at `data/raw/runs/<iso-ts>__<system>/` so they're easy to grep by system.

---

## Model + cost

Both systems default to free `nvidia/nemotron-3-super-120b-a12b:free` (260k context, $0/M tokens) via OpenRouter, with `meta-llama/llama-3.3-70b-instruct:free` as the fallback. Token tallies land in `token_usage` per system per run — the thesis's "output quality per token cost" metric reads from here.

System A uses MASFactory's `LegacyOpenAIModel` adapter (Chat Completions wire). System B uses the OpenAI Python SDK directly. Both end up making the same kind of HTTP call to the same OpenRouter base URL.

---

## Cron schedule

The host's cron drives both systems. Default schedules (see each system's `crontab.sample`):

- **System A (MASFactory):** every 6 hours starting 00:00 → `0 */6 * * *`
- **System B (Hermes):** every 6 hours starting 03:00 → `0 3,9,15,21 * * *`

Offset by 3 hours so they never hit arXiv / the same actor website at the same moment.
