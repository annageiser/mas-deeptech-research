# DNS + dashboard setup — `mas-deeptech-research.cloud`

The dashboard lives at `https://mas-deeptech-research.cloud/`. Caddy in front of the Streamlit container handles TLS via Let's Encrypt automatically — but **only after DNS is pointed at the VPS**. This document covers that step and the deploy.

## Step 1 — Point the domain at the VPS

In your Hostinger control panel (Domains → mas-deeptech-research.cloud → DNS / Nameservers → Manage DNS Records):

| Type | Name | Value | TTL |
|---|---|---|---|
| **A** | `@` | `187.127.87.208` | 3600 |
| **A** (optional) | `www` | `187.127.87.208` | 3600 |

Hit save. DNS propagation usually takes 5–15 minutes; Hostinger's TTL defaults are generally fine.

Verify before continuing:
```bash
dig +short mas-deeptech-research.cloud
# expect: 187.127.87.208
```

If you used a DNS check tool like <https://dnschecker.org>, all global resolvers should show the IP within ~15 min.

## Step 2 — Deploy the dashboard + Caddy

Already in the next compose run. You don't need to do anything — see the deploy commands in `docs/reproducibility.md` Phase 3. The relevant additions are:

```bash
docker compose build dashboard      # ~2 min — installs Streamlit + pyvis + networkx
docker compose up -d dashboard caddy
```

After `docker compose up -d caddy` first runs, Caddy talks to Let's Encrypt's ACME endpoint and provisions a cert. Watch:
```bash
docker compose logs -f caddy
# look for: "certificate obtained successfully"
```

The first cert provision usually takes 20–60 seconds. Subsequent restarts reuse the cached cert (stored in the `caddy_data` Docker volume).

## Step 3 — Verify

Open <https://mas-deeptech-research.cloud/> in a browser.

You should see:
- **Home** page with the topline numbers, dimension chart, token spend over time.
- A sidebar with **System** filter (both / masfactory / hermes) and **Lookback window** slider.
- Three other pages in the sidebar: **Signals explorer**, **Knowledge graph**, **Reports browser**.

The TLS cert lock icon in the browser should be green / closed — no warning.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Browser says "This site can't be reached" | DNS not yet propagated | `dig +short mas-deeptech-research.cloud` should return the VPS IP. If not, wait 10 min and retry. |
| TLS warning (cert signed by unknown CA) | First-cert provisioning still in flight, or LE rate limit | `docker compose logs caddy` will show the error. LE has a 5 attempts / hour limit per domain. |
| `502 Bad Gateway` | Dashboard container not running or crashed | `docker compose ps`; `docker compose logs dashboard --tail=200`. Most common: missing env var, restart container after fixing `.env`. |
| Pages load but tables are empty | Supabase auth working but no signals yet | Run `docker compose run --rm masfactory run-once` manually to generate data. |
| Knowledge graph shows nothing | All signals filtered out by sidebar filters or shared-dimension threshold too high | Lower the threshold slider, expand the lookback window. |

## What runs continuously vs. on-demand

| Container | Lifecycle |
|---|---|
| `caddy` | always up (`restart: unless-stopped`) |
| `dashboard` | always up (`restart: unless-stopped`) |
| `masfactory`, `hermes`, `reports` | exit after each run; cron re-launches |

So `docker compose ps` will normally show only `caddy` and `dashboard` as `Up`. The cron-driven containers appear briefly during their run window and then exit.

## Public-facing security note

- The dashboard reads from Supabase with the **service_role** key. That key never leaves the VPS — it's in `.env`, used by the Streamlit process server-side, and never sent to the browser.
- The dashboard does NOT expose any authentication. Anyone with the URL can read all signals, runs, and tokens.
- For a thesis project that's fine; signals are derived from public sources. If you want auth later, Caddy supports basic auth in two lines, or Streamlit has community auth components.
