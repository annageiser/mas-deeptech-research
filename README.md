# mas-deeptech-research

Bachelor Thesis (Anna Geiser, FHNW, Brugg-Windisch — submission 7 August 2026): two parallel multi-agent systems for mapping the Swiss quantum-computing ecosystem under noncommensurable performance.

| | System A | System B |
| --- | --- | --- |
| **Pattern** | MASFactory (Liu et al., 2026) — orchestration-centric graph | Hermes-pattern (Nous Research, 2025) — memory + skill-centric loop |
| **Path** | [`systems/masfactory/`](systems/masfactory) | [`systems/hermes/`](systems/hermes) |
| **Status** | runnable skeleton, 7-agent graph, 6 tests green | runnable skeleton, single-agent loop + 4 skills, 6 tests green |

Both systems share the same task, the same actor list ([`data/raw/actors.yaml`](data/raw/actors.yaml)), the same Supabase schema ([`systems/masfactory/masfactory_system/persistence/schema.sql`](systems/masfactory/masfactory_system/persistence/schema.sql)), and the same OpenRouter-backed model (free `nvidia/nemotron-3-super-120b-a12b:free`). Their outputs are directly comparable — that is the point.

## Quick links

- [Architecture (both systems)](docs/architecture.md)
- [Hostinger VPS runbook (both containers)](docs/reproducibility.md)
- [SSH-assisted go-live walkthrough](docs/ssh-go-live.md)
- [Methodology](docs/methodology.md)
- [Session log (assistant time + tokens)](docs/session_log.md)

## Layout

```
.
├── data/
│   └── raw/
│       ├── actors.yaml             # 40 Swiss quantum actors (canonical input)
│       └── runs/                   # per-run audit folders, suffixed __masfactory or __hermes
├── docs/
├── evaluation/                     # shared evaluation harness (used after both systems land)
├── systems/
│   ├── masfactory/                 # System A
│   └── hermes/                     # System B
├── tests/
├── docker-compose.yml              # both containers wired
└── .env.example
```

## Running both systems (on a fresh Hostinger Ubuntu VPS)

See [`docs/reproducibility.md`](docs/reproducibility.md) for the full Phase 0 → Phase 5 runbook. The short version:

```bash
git clone https://github.com/annageiser/mas-deeptech-research.git /opt/mas-deeptech-research
cd /opt/mas-deeptech-research

cp .env.example .env && nano .env       # OPENROUTER_API_KEY, SUPABASE_*

# One-shot each system to verify before scheduling cron
docker compose build masfactory hermes
docker compose run --rm masfactory run-once --limit-actors 2
docker compose run --rm hermes    run-once --limit-actors 2

# Schedule both
sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory
sudo cp systems/hermes/crontab.sample     /etc/cron.d/hermes
sudo chmod 0644 /etc/cron.d/masfactory /etc/cron.d/hermes
sudo systemctl restart cron
```

## Running the test suites locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install ./systems/masfactory ./systems/hermes pytest
python -m pytest systems/masfactory/tests/ systems/hermes/tests/ -v
# 12 tests should pass.
```
