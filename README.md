# mas-deeptech-research

Bachelor Thesis (Anna Geiser, FHNW, Brugg-Windisch — submission 7 August 2026): two parallel multi-agent systems for mapping the Swiss quantum-computing ecosystem under noncommensurable performance.

| | System A | System B |
| --- | --- | --- |
| **Pattern** | MASFactory (Liu et al., 2026) — orchestration-centric graph | Hermes Agent (Nous Research, 2026) — memory + skill-centric, real upstream CLI |
| **Path** | [`systems/masfactory/`](systems/masfactory) | [`systems/hermes/`](systems/hermes) (wraps NousResearch/hermes-agent submodule at `systems/hermes/upstream/`) |
| **Status** | Daily 04:00 Europe/Zurich on VPS | Real CLI replaces v0.4.3 pattern impl on 2026-06-10 — see [`docs/iterations/v0.4.4-real-hermes-agent.md`](docs/iterations/v0.4.4-real-hermes-agent.md) |

Both systems share the same task, the same actor list ([`data/raw/actors.yaml`](data/raw/actors.yaml)), the same Supabase schema ([`systems/masfactory/masfactory_system/persistence/schema.sql`](systems/masfactory/masfactory_system/persistence/schema.sql)), and the same OpenRouter-backed model. Their outputs are directly comparable — that is the point.

## Quick links

- [Architecture (both systems)](docs/architecture.md)
- [Methodology — System B is the real upstream CLI](docs/methodology.md)
- [Hostinger VPS runbook (both containers)](docs/reproducibility.md)
- [SSH-assisted go-live walkthrough](docs/ssh-go-live.md)
- [v0.4.4 iteration doc — pattern → real CLI](docs/iterations/v0.4.4-real-hermes-agent.md)
- [Session log (assistant time + tokens)](docs/session_log.md)

## Layout

```
.
├── data/
│   └── raw/
│       ├── actors.yaml             # 40 Swiss quantum actors (canonical input)
│       └── runs/                   # per-run audit folders (System A only — System B writes to its named volume)
├── docs/
├── systems/
│   ├── masfactory/                 # System A — MASFactory graph
│   ├── hermes/                     # System B — wraps NousResearch/hermes-agent (upstream/ submodule)
│   ├── api/                        # FastAPI JSON service over Supabase
│   ├── web/                        # Next.js 14 frontend
│   ├── reports/                    # daily + weekly markdown report generator
│   └── evaluation/                 # Chapter 3.5 evaluation harness
├── docker-compose.yml              # both containers + api + web + caddy + reports
└── .env.example
```

## Running both systems (on a fresh Hostinger Ubuntu VPS)

See [`docs/reproducibility.md`](docs/reproducibility.md) for the full Phase 0 → Phase 5 runbook. The short version:

```bash
git clone https://github.com/annageiser/mas-deeptech-research.git /opt/mas-deeptech-research
cd /opt/mas-deeptech-research
git submodule update --init --depth 1 systems/hermes/upstream

cp .env.example .env && nano .env       # OPENROUTER_API_KEY, SUPABASE_*

# Build everything (Hermes pulls the official image from Docker Hub since v0.4.20 — no upstream build needed)
docker compose build

# Smoke-test each system before scheduling cron
docker compose run --rm masfactory run-once --limit-actors 2
HERMES_LIMIT_ACTORS=2 HERMES_LOOKBACK_DAYS=60 \
  docker compose run --rm hermes

# Schedule both (Europe/Zurich)
sudo cp systems/masfactory/crontab.sample /etc/cron.d/mas-deeptech-research-masfactory
sudo cp systems/hermes/crontab.sample     /etc/cron.d/mas-deeptech-research-hermes
sudo chmod 0644 /etc/cron.d/mas-deeptech-research-*
sudo systemctl restart cron
```

## Running the test suites locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install ./systems/masfactory pytest
python -m pytest systems/masfactory/tests/ -v
# Note: System B is now the real upstream CLI — there are no Python unit tests
# in systems/hermes/ (the wrapper logic is exercised end-to-end on the VPS).
```
