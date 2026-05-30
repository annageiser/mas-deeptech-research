# systems/api — FastAPI JSON service

Read-only JSON API over the shared Supabase signal database. It is the single
data interface for:

- the Next.js frontend (`systems/web`)
- the thesis evaluation scripts (`evaluation/`)

It vendors `scoring.py` + `labels.py` (same pattern the Streamlit dashboard
used — the API container doesn't bundle the masfactory package). The scoring
is the literature-grounded model: impact, **credibility** (cost-discounted
impact), **cheap-talk ratio** (Ehrenthal's research question), authority
(capability vs legitimacy), momentum, diversity.

## Endpoints

```
GET /api/health
GET /api/meta                      → dimensions, channels, cost classes, references (the schema)
GET /api/actors                    → actor catalogue
GET /api/signals?system=&days=&actor=&dimension=&source_kind=&min_confidence=
GET /api/scores?system=&days=      → per-actor score table (impact, credibility, cheap_talk_ratio, …)
GET /api/ecosystem?system=&days=   → top-line hero numbers + category mix + dimension mix
GET /api/signalling?system=&days=  → cheap-talk vs costly-signal analysis (the thesis core)
GET /api/actor/{slug}?system=&days= → one actor's profile, scores, signals, peer rank
GET /api/compare?system=&days=     → System A vs System B head-to-head
GET /api/knowledge-graph?system=&days=&threshold= → nodes + edges JSON
GET /api/reports?kind=&period=     → list / fetch generated markdown reports
```

All query params are optional; sensible defaults (system=both, days=30).

## Run locally

```bash
pip install -e '.[test]'
SUPABASE_URL=... SUPABASE_SERVICE_KEY=... uvicorn api_app.main:app --reload --port 8000
# http://localhost:8000/docs  — interactive OpenAPI
```

## Build-time smoke check

`python -m api_app.selfcheck` imports the app + scoring without network and
prints the route table. The Dockerfile runs it so a broken image never ships.
