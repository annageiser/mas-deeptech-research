# systems/hermes — System B (NousResearch hermes-agent CLI)

The thesis's **memory + skill-centric** comparison candidate. This directory wraps the real [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) CLI (v0.16.0, MIT, pinned via git submodule at `upstream/`) and drives it from cron to collect Swiss-quantum signals.

## History — why this is *not* the pattern impl any more

Until 2026-06-10 this directory held a pattern implementation of the Hermes architecture: a single AIAgent loop in pure Python, SQLite memory, SKILL.md files. It ran daily for several months.

The supervisor question "läuft echter Hermes-Agent oder Nachbildung?" prompted a switch to the actual upstream CLI. The pattern code was deleted; the historical signals it produced (rows in `public.signals` tagged `system='hermes'`) are kept untouched — the new agent writes to the same namespace and inherits the lineage.

Full architectural-decision rationale: [`docs/iterations/v0.4.4-real-hermes-agent.md`](../../docs/iterations/v0.4.4-real-hermes-agent.md).

## Layout

```
systems/hermes/
├── upstream/                                       # git submodule → NousResearch/hermes-agent (source reference; NOT in build chain v0.4.20+)
├── Dockerfile                                      # wrapper image: FROM nousresearch/hermes-agent:v2026.6.5 (digest-pinned)
├── crontab.sample                                  # daily 05:00 Europe/Zurich
├── .gitignore                                      # state/ + __pycache__/
├── config/cli-config.yaml                          # cron-mode config (web+skills only, no chatter)
├── skills/
│   └── collect-swiss-quantum-signals/SKILL.md      # methodology: Ehrenthal 4 + defense, JSON output contract
└── scripts/
    ├── seed-hermes-home.sh                         # cont-init.d hook (copy skill+config into $HERMES_HOME)
    ├── collect_all_actors.sh                       # cron entrypoint: loop actors → `hermes chat -q`
    └── persist_signals.py                          # parse agent stdout JSON → upsert public.signals
```

## How it works (per cron run)

1. `collect_all_actors.sh` reads `/data/raw/actors.yaml` (bind-mounted).
2. For each actor it builds a prompt that names the actor + aliases + website + category.
3. `hermes chat -q --skills collect-swiss-quantum-signals --toolsets web,skills "<prompt>"` runs the real agent in non-interactive single-query mode.
4. The agent uses `web_search` + `web_extract` per the skill, then emits a single JSON block.
5. `persist_signals.py` parses the last fenced ```json``` block (or brace-balanced fallback), validates the four-signal taxonomy, and upserts to `public.signals` with `system='hermes'`. Idempotent via `(actor_slug, content_hash)`.
6. Per-actor stdout + persistence log land in the named-volume mount at `/opt/data/state/runs/<UTC-iso>/`.

## Build + deploy

### Build the wrapper (fast — pulls the official image from Docker Hub)

```bash
docker compose build hermes
```

### Smoke run (3 actors, 60-day window)

```bash
HERMES_LIMIT_ACTORS=3 HERMES_LOOKBACK_DAYS=60 \
  docker compose run --rm hermes
```

Check Supabase:
```sql
SELECT count(*), max(collected_at)
FROM signals
WHERE system='hermes' AND collected_at > now() - interval '1 hour';
```

### Wire up the host cron

```bash
sudo cp systems/hermes/crontab.sample /etc/cron.d/mas-deeptech-research-hermes
sudo chmod 0644 /etc/cron.d/mas-deeptech-research-hermes
sudo systemctl restart cron
```

## Configuration (env vars in `.env`)

| Var | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Required by the agent's OpenRouter provider | — |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Required by `persist_signals.py` | — |
| `HERMES_LIMIT_ACTORS` | Cap actor count (smoke tests). `0` = process all | unset → all |
| `HERMES_LOOKBACK_DAYS` | Days to look back for signals | `180` |
| `HERMES_HOME` | Where the agent stores memory + state | `/opt/data` (volume) |
| `HERMES_MODEL` (override) | OpenRouter model slug | `nvidia/nemotron-nano-9b-v2:free` |

The `config/cli-config.yaml` is copied into `$HERMES_HOME/config.yaml` on first boot via `seed-hermes-home.sh`. Edits to that file in the volume survive container restarts and image rebuilds.

## Architectural invariants

- **No Python imports from `systems/masfactory/`** — comparison-validity invariant. The wrapper uses only `httpx` + `pyyaml` (already in the upstream venv).
- **`system='hermes'`** — every row this agent writes is tagged this way, joining the historical pattern-era rows under one namespace.
- **Hard time budget**: 600 s/actor (shell `timeout`) + `agent.max_turns: 30` in the config + `tool_loop_guardrails.hard_stop_after.same_tool_failure: 5`.
- **Toolset**: only `web` + `skills`. No terminal (security), no browser (Playwright weight), no image_gen/tts (irrelevant).
