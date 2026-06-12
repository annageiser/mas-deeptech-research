# Hostinger VPS runbook — both systems

Phase 0 ➜ Phase 5 below take a fresh Hostinger Ubuntu VPS to a state where both **System A (MASFactory)** and **System B (Hermes Agent)** are running on cron and writing to the same Supabase.

> **Estimated time end-to-end:** ~60 minutes. Most of it is the two `docker compose build` steps (~15 min each) and Supabase provisioning (~10 min).

If you'd rather have me drive the SSH session step-by-step while you watch, see [`docs/ssh-go-live.md`](ssh-go-live.md).

---

## Phase 0 — Provision the VPS and install Docker

1. In the Hostinger control panel, order a **KVM 2** VPS (2 vCPU / 8 GB RAM / 100 GB NVMe — minimum that builds both images comfortably). Choose **Ubuntu 24.04 LTS**.
2. SSH in as root using the password emailed by Hostinger:
   ```bash
   ssh root@<your-vps-ip>
   ```
3. Hostinger has a one-click "Initial server setup" recipe — use it; it's faster than doing it manually. Or do it by hand: create a non-root user, add it to `sudo`, disable root SSH, switch to key-based auth.
4. Install Docker Engine + Compose plugin:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER
   newgrp docker
   docker --version
   docker compose version
   ```
5. Install git:
   ```bash
   sudo apt-get update && sudo apt-get install -y git
   ```

---

## Phase 1 — Clone the repo and prepare `.env`

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/annageiser/mas-deeptech-research.git
sudo chown -R $USER:$USER mas-deeptech-research
cd mas-deeptech-research

cp .env.example .env
nano .env
```

Fill in at minimum:

- `OPENROUTER_API_KEY` — from <https://openrouter.ai/keys>
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — see Phase 2

Leave the model IDs at their defaults unless you have a reason to switch.

---

## Phase 2 — Create the Supabase project and apply the shared schema

1. At <https://supabase.com/dashboard> create a new project (free tier is fine for the thesis timeline).
2. Project Settings → API → copy the **Project URL** into `SUPABASE_URL` and the **service_role** key into `SUPABASE_SERVICE_KEY`. Do **not** use the anon key — both runners need write access.
3. Open the SQL editor and paste the contents of [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql). Run it once. It creates the `actors`, `signals`, `runs`, `token_usage`, and `audit_log` tables, enables the `vector` and `pgcrypto` extensions, AND installs the v0.4.0 migration block (adds `signal_type`, `dimension_legacy` columns; rewrites legacy v0.3.0 dimension keys to v0.4.0; auto-creates `signals_embedding_ivfflat_idx` once embeddings are populated; installs the `find_similar_signals` RPC for semantic dedup). The whole file is idempotent — safe to re-run on existing projects.
4. **On existing deployments** that pre-date v0.4.0, see [`docs/migrations.md`](migrations.md) for the SQL block to paste — applying the full schema.sql works too (idempotent), but `migrations.md` carries the focused block + a verification query.

---

## Phase 3 — Build and one-shot each container

```bash
cd /opt/mas-deeptech-research

# System A
docker compose build masfactory                 # build-time smoke check runs
docker compose run --rm masfactory run-once --limit-actors 2

# System B
docker compose build hermes                     # build-time smoke check runs
docker compose run --rm hermes run-once --limit-actors 2
```

You should see, per run:
```
run <uuid>: kept=N inserted=N audit=/data/raw/runs/<iso-ts>__masfactory
run <uuid>: actors=2 signals_inserted=N audit=/data/raw/runs/<iso-ts>__hermes
```

If a config error is raised, the message tells you which env var is missing. If a run fails inside the graph or the loop, the `data/raw/runs/<ts>__<system>/error.txt` file on the host contains the traceback.

---

## Phase 4 — Install both cron schedules on the host

```bash
sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory
sudo cp systems/hermes/crontab.sample     /etc/cron.d/hermes
sudo chmod 0644 /etc/cron.d/masfactory /etc/cron.d/hermes
sudo systemctl restart cron
```

Default schedules are offset 3 hours apart so the systems never hit arXiv / a website at the same moment:

- MASFactory: `0 */6 * * *` (00:00, 06:00, 12:00, 18:00 UTC)
- Hermes: `0 3,9,15,21 * * *` (03:00, 09:00, 15:00, 21:00 UTC)

---

## Phase 5 — Verification

```bash
# Watch the most recent audit folders.
ls -lt data/raw/runs | head

# Tail recent logs for each system.
sudo tail -n 200 /var/log/masfactory.log
sudo tail -n 200 /var/log/hermes.log

# Confirm rows landed in Supabase (run from the Supabase SQL editor):
#   select system, count(*) from runs group by system;
#   select system, count(*) from runs r join signals s on s.run_id=r.id group by system;
#   select system, node_name, sum(input_tokens), sum(output_tokens)
#     from runs r join token_usage t on t.run_id=r.id
#     group by 1,2 order by 1,2;
```

If `signals` count is zero on a system but the run status is `ok`, the actor selection on that run hit only low-signal actors — bump `MASF_LIMIT_ACTORS` / `HRM_LIMIT_ACTORS` in `.env` and re-run.

---

## Updating either system later

```bash
cd /opt/mas-deeptech-research
git pull
docker compose build masfactory hermes
# Next cron tick picks up the new images automatically. To force one now:
docker compose run --rm masfactory run-once
docker compose run --rm hermes run-once
```

If the pull includes a schema change, check [`docs/migrations.md`](migrations.md) for the SQL block to paste into the Supabase SQL editor. Every migration is idempotent — re-running is a no-op.

---

## Optional capability layers — env reference

All five are off by default. Turn on in `/opt/mas-deeptech-research/.env`, then `docker compose up -d` for the affected service (no rebuild needed unless the dependency changed). Full descriptions in [`docs/architecture.md`](architecture.md) §Optional capability layers.

```bash
# --- pgvector embeddings (~210 MB model download on first call, ~50 ms/signal) ---
MASF_EMBEDDINGS=1
HRM_EMBEDDINGS=1

# --- semantic dedup via cosine NN (requires embeddings on) ---
MASF_SEMANTIC_DEDUP=1
MASF_SEMANTIC_DEDUP_THRESHOLD=0.92   # 0.5..0.999 (clamped)
MASF_SEMANTIC_DEDUP_DAYS=30          # 1..365   (clamped)
HRM_SEMANTIC_DEDUP=1
HRM_SEMANTIC_DEDUP_THRESHOLD=0.92
HRM_SEMANTIC_DEDUP_DAYS=30

# --- consensus Critic (System A only) — Wang et al. 2023, 3× Critic cost ---
MASF_CRITIC_CONSENSUS_PASSES=3

# --- debate Critic (System A only) — Du et al. 2023, requires consensus on, 6× Critic cost ---
MASF_CRITIC_DEBATE_ROUNDS=1

# --- EPO Open Patent Services — free 4 GB/week tier ---
# Register at https://developers.epo.org → create an app → copy keys.
EPO_OPS_CONSUMER_KEY=
EPO_OPS_CONSUMER_SECRET=
```

Each combination is recorded on every run in `data/raw/runs/<ts>__<sys>/config.json` AND in the Supabase `runs.config_snapshot` JSONB column, so the audit trail captures which capability layers were active for any historical run.

## Widening the collection funnel (v0.4.0 defaults)

Per-actor limits raised across the board in v0.4.0; the Critic is correspondingly stricter to keep the persisted corpus clean. Tune via `.env`:

```bash
MASF_LIMIT_ACTORS=40   # full ecosystem
MASF_LIMIT_ARXIV=10    # was 5 in v0.3.0
MASF_LIMIT_WEBSITE=5   # was 2
MASF_LIMIT_NEWS=10     # was 5
MASF_LIMIT_PRESS=10    # was 5 (new in v0.4.0)
MASF_LIMIT_PATENTS=10  # was 5 (only active if EPO_OPS keys set)
HRM_LIMIT_ACTORS=40
HRM_MAX_ITERATIONS=6
```

## Hermes web tools (Tavily / alternates)

System B's agent needs an external search-provider API key to actually use `web_search` + `web_extract`. Without one, the tools register but fail their availability check at call-time, the agent ends up with `Tools: 0`, and every actor returns 0 signals.

Upstream tries six backends in priority order. The simplest free-tier setup is **Tavily** (1,000 credits/month, covers both search and extract on one key).

```bash
# 1. Register: https://app.tavily.com/sign-in → Researcher plan → API Keys → copy tvly-…

# 2. Add to .env on the VPS
echo "TAVILY_API_KEY=tvly-YOUR-KEY-HERE" >> /opt/mas-deeptech-research/.env

# 3. Recreate the hermes container so the new env var lands
cd /opt/mas-deeptech-research
docker compose build hermes      # only needed if image version bumped
HERMES_LIMIT_ACTORS=3 HERMES_LOOKBACK_DAYS=60 docker compose run --rm hermes

# 4. Verify in a fresh hermes shell
docker compose run --rm --entrypoint sh hermes -c \
  'hermes tools list 2>&1 | grep -E "web|✓|✗"'
# expect: ✓ enabled  web  🔍 Web Search & Scraping  (with no "unavailable" debug lines)
```

| Backend | Env var | Free tier | Covers |
| --- | --- | --- | --- |
| **Tavily** (recommended) | `TAVILY_API_KEY` | 1,000/mo | search + extract |
| Exa | `EXA_API_KEY` | 1,000/mo | search + extract |
| Brave (free) | `BRAVE_SEARCH_API_KEY` | 2,000/mo | search only |
| Firecrawl | `FIRECRAWL_API_KEY` | 500/mo | search + extract |
| Parallel | `PARALLEL_API_KEY` | paid | search + extract |
| DuckDuckGo (ddgs) | none — needs `ddgs` Python pkg | unlimited | search only — pkg not in upstream image |

All env vars are wired through `docker-compose.yml`'s `hermes.environment` block; you only need to set the one(s) you have keys for in `.env`.

**Capacity math for cron**: 40 actors × ~6 searches/actor × 4 weekly runs = ~960 searches/month → fits inside Tavily's 1k/mo. Daily cron (~7,200/mo) exceeds every free tier — schedule **weekly** unless you upgrade. The shipped crontab.sample is daily-cron; flip the cron expression to `0 5 * * 1` (Mondays 05:00 Europe/Zurich) for weekly.

## Site auth (basic)

The public site lives behind Caddy basic auth — see [`caddy/Caddyfile`](../caddy/Caddyfile).

The shipped Caddyfile has a clearly-marked **placeholder hash** that must be replaced before the gate is meaningful. Rotate on first deploy:

```bash
# On the VPS — generate a fresh bcrypt hash
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext "<your-password>"
# → prints  $2a$14$...

# Paste the hash into caddy/Caddyfile, replacing the line containing
# "PLACEHOLDER_HASH_REPLACE_BEFORE_DEPLOY". You can use sed:
sed -i 's|\$2a\$14\$PLACEHOLDER_HASH_REPLACE_BEFORE_DEPLOY___________________|<paste-real-hash>|' caddy/Caddyfile

# ━━━ CRITICAL: USE RESTART, NOT RELOAD ━━━
docker compose restart caddy
sleep 4

# Verify
curl -I https://mas-deeptech-research.cloud         # expect HTTP/2 401
curl -I -u "anna:<your-password>" https://mas-deeptech-research.cloud   # expect HTTP/2 200
```

### Why `restart`, not `reload`?

In a Caddy 2.10-alpine container behind docker-compose, `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` returns success ("config loaded") but leaves the **running in-memory config untouched**. The Caddyfile parser produces JSON, but Caddy's admin API logs `"config is unchanged"` because it compares to a stale baseline. The result: edits to the Caddyfile silently never take effect via `reload`.

This was discovered after 3+ hours of debugging Caddy's `basicauth` syntax on 2026-06-11. The Caddyfile syntax was correct the whole time. The fix is to use `docker compose restart caddy` after any edit to `caddy/Caddyfile`. Restart re-reads the file from scratch and the new config takes effect immediately.

### Layout notes

By default the auth gates **every** route, including `/api/*`. If you need the API to stay open (e.g. so an external evaluator script can hit it without credentials), move the `basicauth` directive INSIDE the `handle` block you want to gate, not at the site level — and `restart` afterwards.

If you ever see `curl -I https://mas-deeptech-research.cloud` return `200` instead of `401`, the running Caddy has stale config. `docker compose restart caddy` fixes it.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `config error: environment variable OPENROUTER_API_KEY is required` | `.env` not loaded or empty | `cat .env`; ensure compose reads `env_file: .env` (already wired). |
| `httpx.HTTPStatusError` on Supabase write | Used anon key instead of service_role | Replace `SUPABASE_SERVICE_KEY` with the service-role key. |
| Image build fails at the `build-check` step | Bug in graph (A) or skill files (B) | Run `pip install ./systems/<sys> && python -m <sys>_system.runner build-check` locally to reproduce. |
| `429 Too Many Requests` from OpenRouter | Free Nemotron tier exhausted | Fallback model auto-takes over; if persistent, set `MASF_MODEL_MAIN` (or `HRM_MODEL_MAIN`) to the fallback ID temporarily. |
| Empty audit folders | Cron not running | `sudo systemctl status cron`; `sudo journalctl -u cron --since "1 hour ago"`. |
| System B's `iterations_used == HRM_MAX_ITERATIONS` and `stopped_reason == "max_iterations"` | The agent never called `finish_actor` | Inspect `data/raw/runs/<ts>__hermes/actor_<slug>.json` transcript; usually the model refused to produce strict JSON. Raise `HRM_MAX_ITERATIONS` slightly or tweak the `parallel-cli` skill's procedure. |
