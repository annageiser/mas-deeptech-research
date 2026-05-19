# Hostinger VPS runbook — System A

Phase 0 ➜ Phase 5 below take a fresh Hostinger Ubuntu VPS to a running MASFactory pipeline that writes Swiss-quantum signals to Supabase every 6 hours.

> **Estimated time end-to-end:** ~45 minutes, most of which is the first `docker compose build` (≈15 min) and Supabase project provisioning (≈10 min).

---

## Phase 0 — Provision the VPS and install Docker

1. In the Hostinger control panel, order a **KVM 2** VPS (2 vCPU / 8 GB RAM / 100 GB NVMe — the minimum that builds the masfactory image comfortably). Choose **Ubuntu 24.04 LTS**.
2. SSH in as root using the password emailed by Hostinger:
   ```bash
   ssh root@<your-vps-ip>
   ```
3. Create a non-root user and lock down SSH (Hostinger has a one-click "Initial server setup" recipe — use it; it's faster than doing it manually).
4. Install Docker Engine + Compose plugin (the snap version is older — use the official repo):
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
sudo git clone https://github.com/<your-org>/mas-deeptech-research.git
sudo chown -R $USER:$USER mas-deeptech-research
cd mas-deeptech-research

cp .env.example .env
nano .env
```

Fill in at minimum:

- `OPENROUTER_API_KEY` — from <https://openrouter.ai/keys>
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — see Phase 2

Leave `MASF_MODEL_MAIN` and `MASF_MODEL_FALLBACK` at their defaults unless you have a reason to switch.

---

## Phase 2 — Create the Supabase project and apply the schema

1. At <https://supabase.com/dashboard> create a new project (free tier is fine for the thesis timeline).
2. Project Settings → API → copy the **Project URL** into `SUPABASE_URL` and the **service_role** key into `SUPABASE_SERVICE_KEY`. Do **not** use the anon key — the runner needs write access.
3. Open the SQL editor and paste the contents of [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql). Run it once. It creates the `actors`, `signals`, `runs`, `token_usage`, and `audit_log` tables and enables the `vector` and `pgcrypto` extensions.
4. (Optional) After a few runs have populated the `embedding` column, create the IVF flat index commented at the bottom of the SQL file. Doing it earlier is wasted — `ivfflat` builds badly on empty tables.

---

## Phase 3 — Build and run the container

```bash
cd /opt/mas-deeptech-research

# Build (the Dockerfile runs `runner build-check` in the final layer, so a
# broken graph fails the build instead of failing at first invocation).
docker compose build masfactory

# Manual one-shot to verify env wiring. The first run can take 2-3 minutes
# while arXiv responses come in.
docker compose run --rm masfactory run-once --limit-actors 2

# You should see something like:
#   run 1c4a...: kept=4 inserted=4 audit=/data/raw/runs/2026-05-19T09-15-02Z
```

If the run fails on a config error, the message tells you which env var is missing. If it fails inside the graph, the `data/raw/runs/<ts>/error.txt` file on the host contains the traceback (the `data/` directory is bind-mounted into the container).

---

## Phase 4 — Install the cron schedule on the host

```bash
sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory
sudo chmod 0644 /etc/cron.d/masfactory
sudo systemctl restart cron

# Check the next scheduled run:
sudo systemctl status cron --no-pager | grep -i cron
```

The default schedule is every 6 hours. Edit `/etc/cron.d/masfactory` directly if you need a different cadence.

---

## Phase 5 — Verification

```bash
# Watch the most recent audit folder appear after the next cron tick.
ls -lt data/raw/runs | head

# Tail the container's most recent log.
docker compose logs --tail=200 masfactory

# Confirm rows landed in Supabase.
# Run from the Supabase SQL editor:
#
#   select count(*) from signals;
#   select dimension, count(*) from signals group by dimension order by 2 desc;
#   select node_name, input_tokens, output_tokens
#     from token_usage
#     where run_id = (select id from runs order by started_at desc limit 1);
```

If the `signals` count is zero but the run finished `ok`, the Critic likely dropped everything for the small actor sample — bump `MASF_LIMIT_ACTORS` in `.env` and re-run.

---

## Updating the system later

```bash
cd /opt/mas-deeptech-research
git pull
docker compose build masfactory     # build-check runs again on rebuild
# The next cron tick picks up the new image. To force one now:
docker compose run --rm masfactory run-once
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `config error: environment variable OPENROUTER_API_KEY is required` | `.env` not loaded or empty | `cat .env` to confirm; ensure compose reads `env_file: .env` (already wired). |
| `httpx.HTTPStatusError` on Supabase write | Used anon key instead of service_role | Replace `SUPABASE_SERVICE_KEY` with the service-role key. |
| Build fails at `RUN python -m masfactory_system.runner build-check` | Bug introduced in graph wiring | Run `pip install ./systems/masfactory && python -m masfactory_system.runner build-check` locally to reproduce. |
| `429 Too Many Requests` from OpenRouter | Free Nemotron tier exhausted | The fallback model takes over automatically; if you see persistent failures, set `MASF_MODEL_MAIN` to the fallback ID temporarily. |
| Empty audit folders | Cron not running | `sudo systemctl status cron`; check `/var/log/syslog | grep CRON`. |
