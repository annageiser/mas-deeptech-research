# systems/reports — shared report generator

Container C. Reads the shared Supabase tables (and, for the thesis weekly, the git log of this repo), synthesises via OpenRouter, writes markdown reports to `data/reports/` on the host bind-mount.

This is the only piece of code that touches BOTH systems' data, by design — it's a synthesis layer, not part of either pipeline.

## Modes

```bash
reports-run daily --system masfactory     # writes data/reports/daily/YYYY-MM-DD/masfactory.md
reports-run daily --system hermes         # writes data/reports/daily/YYYY-MM-DD/hermes.md
reports-run weekly --system masfactory    # writes data/reports/weekly/YYYY-WW/masfactory.md
reports-run weekly --system hermes        # writes data/reports/weekly/YYYY-WW/hermes.md
reports-run weekly-thesis                 # writes data/reports/thesis/YYYY-WW/progress.md
reports-run build-check                   # smoke (no network)
```

## How the data flows

```
Supabase (runs, signals, token_usage, audit_log)
            │
            │ supabase-py REST (read-only)
            ▼
    reports_system.supabase_reader
            │
            │ +  git log --since=...  (thesis-weekly only)
            │ +  data/raw/thesis_notes.md  (thesis-weekly only)
            ▼
    reports_system.openrouter   ─── calls Nemotron via OpenRouter
            │
            ▼
    data/reports/<kind>/<period>/<name>.md
```

Prompts live in `prompts/`, one per report type — edit those to change the voice or section structure without touching Python.

## Why a separate container

System A and System B must stay code-independent so the comparative metrics are fair. Reports are *downstream* of both — they read what's already in Supabase, they don't influence what either system produces. Putting reports in a third container keeps the two upstream systems untouched while giving Anna a single place to evolve the synthesis logic.

## Delivery (currently file-only)

Reports land on the VPS's bind-mounted `data/reports/`. To read them:
- `ssh annageiser@vps 'cat /opt/mas-deeptech-research/data/reports/daily/2026-05-21/masfactory.md'`
- Or `scp -r annageiser@vps:/opt/mas-deeptech-research/data/reports/ ~/Documents/thesis-reports/`

TODO (later session): auto-commit to a GitHub branch, email via SMTP, or Telegram delivery.
