# systems/evaluation — empirical-evaluation harness

The spine of **Chapter 3.5 (Empirical Results)** of the BSc thesis. Reads the same Supabase the two MAS systems write to and produces a single `results.json` (machine-readable) + `results.md` (thesis-ready) per invocation.

## The four metrics

| # | Metric | What it answers | Needs gold set? |
|---|---|---|---|
| 1 | **Inter-system agreement** | "How much do System A and System B find the same things on the same task?" — per-actor Jaccard over the set of `source_url` survivors, macro-averaged and weighted by union size. | No — works today. |
| 2 | **Token efficiency** | "Signals persisted per 1 000 LLM tokens" — the *volume* leg of the disposition's "output quality per token cost" metric. | No — works today. |
| 3 | **Classification quality** | Per-system precision / recall / F1 / accuracy + Cohen's κ on `signal_type` (4-way), `dimension` (19-way), and the Critic's keep decision, against the hand-labelled gold set. | **Yes** — see [`data/gold/labels.yaml.example`](data/gold/labels.yaml.example). |
| 4 | **Reproducibility** | Re-run Jaccard on signal-tuples for matched (system, cohort, config) run pairs. Calibrates the credibility-mechanism story: the world isn't reproducible, so neither is a system that observes it. | No — works once ≥ 2 successful runs exist for any cohort. |

Each metric is a standalone pure-Python module in `eval_app/metrics/`; the runner orchestrates them and `report.py` renders the markdown. The harness degrades gracefully — missing gold set, no overlap with the window, no re-run pairs yet, etc., all produce structured "not yet" markers rather than empty cells.

## Running it

```bash
cd systems/evaluation
pip install .                                    # one-time
SUPABASE_URL=...  SUPABASE_SERVICE_KEY=... \
EVAL_WINDOW_DAYS=90 \
EVAL_OUTPUT_DIR=data/eval \
EVAL_GOLD_PATH=data/gold/labels.yaml \
python -m eval_app.runner all
```

Output:

```
data/eval/2026-06-09T18-15-22/
├── results.json    # machine-readable, full nested structure, paste into a notebook
└── results.md      # thesis-ready summary, paste into Chapter 3.5
```

Both files carry the full settings + frame counts that produced them, so re-running with the same window and the same Supabase snapshot reproduces the same numbers (modulo Supabase data that landed in between).

## Sub-commands

```bash
python -m eval_app.runner all   # default
python -m eval_app.runner isa   # inter-system agreement only
python -m eval_app.runner tok   # token efficiency only
python -m eval_app.runner rep   # reproducibility only
python -m eval_app.runner cls   # classification quality vs gold
python -m eval_app.runner dump  # write raw Supabase frames as parquet (debug)
```

## Creating the gold set

Stratified-random 50-signal protocol from [`docs/open-questions.md`](../../docs/open-questions.md) §Q1.1:

1. Hit `/api/signals?days=90&limit=1000` (or browse `/signals` on the live site).
2. Bucket the returned signals by (`actor.category`, `signal_type`) — 4×4 = 16 cells.
3. Sample ≥ 3 per cell (where the corpus permits). Total ~50.
4. For each sampled signal, hand-fill the gold YAML row (see [`data/gold/labels.yaml.example`](data/gold/labels.yaml.example)).
5. Save as `data/gold/labels.yaml` (drop the `.example`).
6. Run `python -m eval_app.runner cls`.

Inter-rater reliability tip: ask the supervisor to label a 10-15 row sub-sample independently; compute Cohen's κ between the two label streams to report inter-rater agreement (standard statistic for categorical labels).

## Why this is the right place

The harness is intentionally a **standalone Python package** (not nested inside `systems/api` or `systems/masfactory`) so:

- It cannot accidentally import code from the systems it's evaluating — keeps the comparative-validity invariant clean.
- It can be cron'd separately at a slower cadence than the daily scrapers (e.g. once a week, after the Sunday weekly reports).
- It can be pip-installed by a reviewer from a fresh git clone without booting either MAS.

## Citing in the thesis

Each `results.md` carries the exact UTC timestamp and `EVAL_WINDOW_DAYS` setting. Chapter 3.5 can cite:

> "All numbers in this section are reproducible from the harness in `systems/evaluation/`. The frozen-for-defence run is at `data/eval/2026-06-25T<...>/results.json`; numbers in the body are quoted from `results.md` in the same folder."

This is the operational definition of reproducibility required by the constructive-research methodology (Kasanen et al. 1993).
