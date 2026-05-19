# Hostinger VPS runbook — both systems

Phase 0 ➜ Phase 5 below take a fresh Hostinger Ubuntu VPS to a state where both **System A (MASFactory)** and **System B (Hermes-pattern)** are running on cron and writing to the same Supabase.

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
3. Open the SQL editor and paste the contents of [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql). Run it once. It creates the `actors`, `signals`, `runs`, `token_usage`, and `audit_log` tables and enables the `vector` and `pgcrypto` extensions.
4. (Optional) After a few runs have populated the `embedding` column, create the IVF flat index commented at the bottom of the SQL file.

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

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `config error: environment variable OPENROUTER_API_KEY is required` | `.env` not loaded or empty | `cat .env`; ensure compose reads `env_file: .env` (already wired). |
| `httpx.HTTPStatusError` on Supabase write | Used anon key instead of service_role | Replace `SUPABASE_SERVICE_KEY` with the service-role key. |
| Image build fails at the `build-check` step | Bug in graph (A) or skill files (B) | Run `pip install ./systems/<sys> && python -m <sys>_system.runner build-check` locally to reproduce. |
| `429 Too Many Requests` from OpenRouter | Free Nemotron tier exhausted | Fallback model auto-takes over; if persistent, set `MASF_MODEL_MAIN` (or `HRM_MODEL_MAIN`) to the fallback ID temporarily. |
| Empty audit folders | Cron not running | `sudo systemctl status cron`; `sudo journalctl -u cron --since "1 hour ago"`. |
| System B's `iterations_used == HRM_MAX_ITERATIONS` and `stopped_reason == "max_iterations"` | The agent never called `finish_actor` | Inspect `data/raw/runs/<ts>__hermes/actor_<slug>.json` transcript; usually the model refused to produce strict JSON. Raise `HRM_MAX_ITERATIONS` slightly or tweak the `parallel-cli` skill's procedure. |
