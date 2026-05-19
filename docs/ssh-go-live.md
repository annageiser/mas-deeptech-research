# SSH-assisted go-live — walkthrough

This is the play-by-play for the deployment session when **you grant me SSH access to your Hostinger VPS and I drive while you watch**. Every command is explained before it runs, with rollback notes for each phase. You can stop me at any step.

You will need to have done these things **before** the session:

1. **Provisioned the Hostinger VPS** (KVM 2, Ubuntu 24.04). Have the **IP address** ready.
2. **Created your Supabase project** and copied the **Project URL** and **service_role key**. (Don't paste them into the chat — we'll put them straight into `.env` on the VPS.)
3. **Obtained an OpenRouter API key** at <https://openrouter.ai/keys>.
4. **Added my SSH public key to the VPS** (`~/.ssh/authorized_keys` for the user account, *not* root). I'll send you the public key separately when we start.

Once those four are done, we start the session.

---

## Step 0 — Hello world / I can reach the box

I'll run from my side:
```bash
ssh -o StrictHostKeyChecking=accept-new <user>@<vps-ip> 'hostname && cat /etc/os-release | head -3'
```
**Purpose:** confirm SSH works and we're on Ubuntu 24.04.
**Rollback:** none — this is read-only.

---

## Step 1 — Sanity-check Docker

```bash
ssh <user>@<vps-ip> 'docker --version && docker compose version && groups'
```
**Purpose:** confirm Docker is installed and our user is in the `docker` group (so we don't need sudo for compose commands).
**If it fails:** I'll install Docker via `curl -fsSL https://get.docker.com | sudo sh` and add the user with `sudo usermod -aG docker $USER`. You'll need to log out and back in once for the group change to take effect.

---

## Step 2 — Clone the repo

```bash
ssh <user>@<vps-ip> 'sudo mkdir -p /opt && sudo chown $USER /opt && cd /opt && git clone https://github.com/annageiser/mas-deeptech-research.git'
```
**Purpose:** put the code at `/opt/mas-deeptech-research` (the path baked into the `crontab.sample` files).
**Rollback:** `rm -rf /opt/mas-deeptech-research`. Nothing else on the VPS is affected.

---

## Step 3 — Write `.env`

This is the one step where I'll need your secrets. We have two safe options:

**Option A (recommended): you write `.env` yourself in a separate terminal.** I'll wait. You SSH in, `cd /opt/mas-deeptech-research && cp .env.example .env && nano .env`, paste the three secrets, save. Then tell me to continue.

**Option B: you paste secrets into a one-time chat message, I write them to `.env` and immediately delete them from the conversation context.** Less ideal because secrets touch the chat transcript.

**Verification (no secrets shown):**
```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && grep -E "^(OPENROUTER_API_KEY|SUPABASE_URL|SUPABASE_SERVICE_KEY)=" .env | sed -E "s/=(.{4}).*/=\\1…(redacted)/"'
```
**Purpose:** confirm the three required variables are non-empty without printing the values.

---

## Step 4 — Apply the Supabase schema

I do **not** need Supabase credentials for this step — *you* run it because the SQL editor is in your dashboard.

**You do:**
1. Open <https://supabase.com/dashboard>, pick the project, open the **SQL editor**.
2. Copy the contents of [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) and paste into a new query.
3. Click **Run**.
4. Verify by running `select count(*) from actors;` — it should return 0, and the query should succeed (not error).

Tell me when done, then I continue.

**Rollback:** the schema is idempotent (`create table if not exists`). Re-running is safe. To wipe and start over: `drop table actors, signals, runs, token_usage, audit_log cascade;` in the SQL editor.

---

## Step 5 — Build System A image

```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && docker compose build masfactory'
```
**Purpose:** build Container A. Takes 5–15 min on first build (downloads Python deps, installs masfactory + supabase + httpx + selectolax). The Dockerfile runs `runner build-check` in its final layer, so if anything is broken we find out now.
**Rollback:** `docker image rm mas-deeptech-research/masfactory:0.1.0`. Doesn't touch your data.

---

## Step 6 — Manual one-shot of System A

```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && docker compose run --rm masfactory run-once --limit-actors 2'
```
**Purpose:** end-to-end smoke. Processes 2 actors, hits arXiv + websites, calls OpenRouter, writes to Supabase. Expected output:
```
run <uuid>: kept=N inserted=N audit=/data/raw/runs/<iso-ts>__masfactory
```
**If it fails:** I'll inspect `data/raw/runs/<latest>__masfactory/error.txt` and `actor_pool.json` to triage. Common causes: missing service-role key, schema not applied, Nemotron rate-limited (fallback should auto-take over).
**Rollback:** delete the failed run from Supabase with `delete from runs where status='error';`.

---

## Step 7 — Build System B image

```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && docker compose build hermes'
```
**Purpose:** build Container B. Takes 3–8 min (similar Python stack, lighter than A because no MASFactory).
**Rollback:** `docker image rm mas-deeptech-research/hermes:0.1.0`.

---

## Step 8 — Manual one-shot of System B

```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && docker compose run --rm hermes run-once --limit-actors 2'
```
**Purpose:** same as Step 6, but the agent-loop variant. Expected:
```
run <uuid>: actors=2 signals_inserted=N audit=/data/raw/runs/<iso-ts>__hermes
```
**If it fails with `stopped_reason: "max_iterations"` for every actor:** the agent isn't producing strict JSON. We'll either bump `HRM_MAX_ITERATIONS` or sharpen the `parallel-cli` skill's procedure. Iterate one prompt at a time.

---

## Step 9 — Cross-check in Supabase

You run in the SQL editor:
```sql
select system, count(*) as runs from runs group by system;
select system, count(*) as signals
  from runs r join signals s on s.run_id=r.id
  group by system;
select system, sum(input_tokens)::int as in_tok, sum(output_tokens)::int as out_tok
  from runs r join token_usage t on t.run_id=r.id
  group by system;
```
You should see two `runs` (one per system), some `signals` against each, and non-zero token counts. This is the moment we say "the comparative pipeline works".

---

## Step 10 — Install both cron schedules

```bash
ssh <user>@<vps-ip> 'cd /opt/mas-deeptech-research && \
  sudo cp systems/masfactory/crontab.sample /etc/cron.d/masfactory && \
  sudo cp systems/hermes/crontab.sample     /etc/cron.d/hermes && \
  sudo chmod 0644 /etc/cron.d/masfactory /etc/cron.d/hermes && \
  sudo systemctl restart cron'
```
**Purpose:** the host's cron daemon will now invoke each system on its schedule. From this moment on, both systems are *live* — they run continuously over the disposition's "minimum two-month operational window".
**Rollback:** `sudo rm /etc/cron.d/{masfactory,hermes} && sudo systemctl restart cron`. Stops further cron invocations immediately; existing data stays in Supabase.

---

## Step 11 — Update the session log + push

I'll commit the deployment timestamp and the first-real-run audit summaries into `docs/session_log.md` so the thesis audit trail records "went live on date X".

**Rollback:** standard `git revert` if anything in the log is wrong.

---

## After we hang up — what to monitor for the next 24 hours

1. **Cron fired both systems at least once.** Check `data/raw/runs/` for at least one new `__masfactory` and one new `__hermes` folder.
2. **No `runs.status = 'error'` rows.** SQL: `select count(*) from runs where status='error';` should return 0.
3. **OpenRouter free-tier hasn't dried up.** SQL: `select sum(input_tokens+output_tokens) from token_usage;`. Free Nemotron is generous but not infinite.
4. **Audit folders are accumulating.** Each cron tick should produce one new folder per system, ~5–50 MB depending on signal volume.

If anything looks off, paste the symptom into a new Claude Code session and I'll triage.

---

## What I will NOT do during the SSH session

- I won't `rm -rf` anything outside `/opt/mas-deeptech-research`.
- I won't install global system packages without saying so first.
- I won't store your secrets anywhere except in the `/opt/mas-deeptech-research/.env` file on your VPS (which is already in `.gitignore`).
- I won't push directly to `main` — all my git operations from inside the VPS will be read-only (clones, pulls).
