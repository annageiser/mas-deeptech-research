# System A — MASFactory pipeline

The orchestration-centric half of the BSc thesis (Anna Geiser, FHNW). Runs in a single Docker container on a Hostinger Ubuntu VPS, harvests public signals about Swiss quantum-computing actors from arXiv + their websites, classifies them, and persists to Supabase.

| Where to look | What you'll find |
| --- | --- |
| [`docs/architecture.md`](../../docs/architecture.md) | Diagram and per-node responsibilities. |
| [`docs/reproducibility.md`](../../docs/reproducibility.md) | Phase 0 → Phase 5 runbook from fresh VPS to a running cron schedule. |
| [`docs/methodology.md`](../../docs/methodology.md) | How this skeleton instantiates the disposition's constructive-research approach. |
| `masfactory_system/agents/` | The 7 node definitions (5 Agents + 2 CustomNodes). |
| `masfactory_system/graph.py` | RootGraph wiring. |
| `masfactory_system/persistence/schema.sql` | Supabase schema (apply once in the Supabase SQL editor). |
| `crontab.sample` | Host-side cron entry that re-invokes the container every 6 hours. |

## TL;DR commands (on the VPS)

```bash
cp .env.example .env && nano .env       # fill OPENROUTER_API_KEY, SUPABASE_*
docker compose build masfactory          # smoke-check runs during build
docker compose run --rm masfactory run-once --limit-actors 2
sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory
```

See the runbook for the full sequence.
