# mas-deeptech-research

Bachelor Thesis (Anna Geiser, FHNW, Brugg-Windisch — submission 7 August 2026): two parallel multi-agent systems for mapping the Swiss quantum-computing ecosystem under noncommensurable performance.

| | System A | System B |
| --- | --- | --- |
| **Framework** | MASFactory (Liu et al., 2026) — orchestration-centric graph | Hermes Agent (Nous Research, 2025) — memory- and skill-centric |
| **Path** | [`systems/masfactory/`](systems/masfactory) | [`systems/hermes/`](systems/hermes) (TODO) |
| **Status** | runnable skeleton, 7-agent graph, OpenRouter + Supabase wired | not yet implemented |

Both systems share the same task, the same actor list ([`data/raw/actors.yaml`](data/raw/actors.yaml)), the same Supabase schema ([`systems/masfactory/masfactory_system/persistence/schema.sql`](systems/masfactory/masfactory_system/persistence/schema.sql)), and the same OpenRouter-backed model (free `nvidia/nemotron-3-super-120b-a12b:free`). Their outputs are directly comparable — that is the point.

## Quick links

- [Architecture](docs/architecture.md)
- [Hostinger VPS runbook](docs/reproducibility.md)
- [Methodology](docs/methodology.md)
- [Session log (assistant time + tokens)](docs/session_log.md)
- [Plan that produced this skeleton](.claude/plans/sharded-rolling-newt.md)

## Layout

```
.
├── data/
│   └── raw/
│       ├── actors.yaml             # 40 Swiss quantum actors (canonical input)
│       ├── runs/                   # one folder per g.invoke() — audit trail
│       └── web_cache/              # deterministic re-runs of the website collector
├── docs/
├── evaluation/                     # shared evaluation harness (used after both systems land)
├── systems/
│   ├── masfactory/                 # System A (this skeleton)
│   └── hermes/                     # System B (TODO)
├── tests/
├── docker-compose.yml              # Container A defined; Container B stubbed
└── .env.example
```

## Running

See [`docs/reproducibility.md`](docs/reproducibility.md). The short version, on a fresh Hostinger Ubuntu VPS:

```bash
git clone <this-repo> /opt/mas-deeptech-research && cd /opt/mas-deeptech-research
cp .env.example .env && nano .env       # OPENROUTER_API_KEY, SUPABASE_*
docker compose build masfactory
docker compose run --rm masfactory run-once --limit-actors 2
sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory
```
