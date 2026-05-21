# systems/dashboard — Streamlit web UI

Container D. Read-only view onto the live Supabase signals + the on-disk reports. Served at `https://mas-deeptech-research.cloud/` via Caddy reverse proxy.

## Pages

| Page | What it shows |
|---|---|
| **Overview** | Top-line counts per system, dimension mix, run health, token spend. |
| **Signals explorer** | Filterable table of every signal: per-system, per-actor, per-dimension, with the evidence quote and source link. |
| **Knowledge graph** | Network of actors + their signal dimensions, edges weighted by co-occurrence. Pyvis HTML embedded. |
| **Reports browser** | Lists all daily / weekly / thesis reports from `data/reports/`. Click to read inline. |

## Why read-only

The dashboard never writes to Supabase — only reads. That keeps the comparative validity intact: the dashboard's existence cannot influence either system's outputs.

## Running outside Docker (for development)

```bash
pip install ./systems/dashboard
OPENROUTER_API_KEY=x SUPABASE_URL=https://… SUPABASE_SERVICE_KEY=… streamlit run systems/dashboard/dashboard_app/Home.py
```

In production it runs in a Docker container started by `docker compose up -d dashboard caddy`.
