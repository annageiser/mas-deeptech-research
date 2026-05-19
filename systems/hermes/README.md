# System B — Hermes-pattern agent

The memory- and skill-centric half of the BSc thesis (Anna Geiser, FHNW). A single long-running AIAgent loop, procedural memory in SQLite, skills as `SKILL.md` files (agentskills.io format), all wrapped in one Docker container running on the same Hostinger VPS as System A.

> **Design note:** the disposition cites Hermes Agent (Nous Research, 2025) as the *exemplar* of this architectural philosophy. The actual `hermes-agent` CLI from Nous Research is a heavy interactive assistant (chat gateways for Telegram/Discord/Slack, ~3500 source files). For a cron-driven batch task it's the wrong shape. This system follows the Hermes *pattern* (single AIAgent loop + procedural memory + agentskills.io SKILL.md files) without depending on the heavy CLI — keeping the comparison with System A fair (both end up as ~comparable Python processes that call OpenRouter and write to the same Supabase tables). See [docs/methodology.md](../../docs/methodology.md) for the full rationale.

## Component map (mirrors the architecture diagram)

| Diagram label | Implementation |
| --- | --- |
| Entry Points + Gateway | `hermes_system/entry_points/` + `runner.py` (CLI). Telegram is a stub. |
| AIAgent (Core Loop) | `hermes_system/agent/core_loop.py` |
| Tools Registry | `hermes_system/tools_registry/registry.py` |
| Skills Loader | `hermes_system/skills_loader/loader.py` |
| Memory Manager | `hermes_system/memory/sqlite_manager.py` (SQLite) |
| Providers (Model API) | `hermes_system/providers/openrouter.py` (OpenAI SDK → OpenRouter) |
| Skills (arxiv, scrapling, parallel-cli, research-paper-writing) | `skills/<name>/SKILL.md` |
| Execution Environments: Docker | this container; SSH commands not wired (out of scope) |

## TL;DR commands (on the VPS)

```bash
docker compose build hermes
docker compose run --rm hermes run-once --limit-actors 2
```

See [docs/reproducibility.md](../../docs/reproducibility.md) for the full runbook covering both containers.
