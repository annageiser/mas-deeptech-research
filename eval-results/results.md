# Evaluation results — 2026-08-03T03-42-35 UTC

Computed by `python -m eval_app.runner all` from the live Supabase. Settings + window are recorded in `results.json` for full reproducibility.

## Inter-system agreement (Jaccard over signal source_url, per actor)

- Actors with signals from **both** systems: **39**
- Actors with signals from **only System A**: 0
- Actors with signals from **only System B**: 1
- **Macro Jaccard** (mean across actors): **0.0434**
- **Weighted Jaccard** (weighted by union size): **0.0386**

Interpretation: a Jaccard of 1.0 means perfect overlap; 0.0 means disjoint signal sets. 
The thesis reports this as the answer to 'how much do the two architectures find the same things on the same task?'

## Token efficiency (signals persisted per 1 000 LLM tokens)

> **Diese Zahl ist nicht belastbar.**
>
> - System B has token data for only 26% of its successful runs, while its signal count is complete. Its efficiency is overstated by roughly 3.9x.
> - Coverage differs between the systems (99% vs 26%). A ratio across unequal denominators measures the bookkeeping, not the systems.
> - Only System A writes public.token_usage. System B's usage lives in the Hermes CLI's own state.db `sessions` table and is not copied into Supabase; see docs/ergebnisse-zusammenfassung.md section 3.1 for the recovery query and the corrected figure.


| System | Signals | Input tokens | Output tokens | Total | **Signals / 1k tokens** |
|---|---:|---:|---:|---:|---:|
| System A · MASFactory | 1008 | 40,992,360 | 23,582,578 | 64,574,938 | **0.0156** |
| System B · Hermes | 2335 | 14,995,592 | 1,899,209 | 16,894,801 | **0.1382** |

- **System A − System B** (signals / 1k tokens): -0.1226
- **Ratio A / B**: 0.113× (>1 means System A is more token-efficient)

Caveat: this is the *volume* leg of the disposition's 'output quality per token cost' metric. 
The thesis's headline efficiency number combines this with the gold-set classification quality below.

## Classification quality (vs hand-labelled gold set)

**Gold set pending.** No gold set present at the configured path. Create data/gold/labels.yaml from data/gold/labels.yaml.example, label ≥ 50 signals across the 4 actor categories × 4 signal types (≥ 3 per cell where possible), and re-run.

## Reproducibility (re-run Jaccard over each run's FOUND set)

| System | # comparisons | Jaccard mean | min | max |
|---|---:|---:|---:|---:|
| masfactory | 12 | 0.4996 | 0.2268 | 0.6182 |
| hermes | 12 | 0.12 | 0.0 | 0.5 |

Interpretation: a re-run Jaccard < 1.0 reflects (a) model non-determinism at temperature > 0 and (b) underlying source-list freshness (Google News / Bing News rotate hourly). The metric calibrates the credibility-mechanism story — even a system fed exclusively costly signals doesn't reproduce 100% because the *world* isn't reproducible.

Basis: consecutive runs of the same system, compared on the (actor, source_url) pairs each run FOUND, restricted to actors both runs attempted. Computed from the run artefacts (System A's audit folders, System B's per-actor agent output), NOT from `public.signals`. Signals attach to the run that first inserted them, so a re-run that rediscovers the same URL contributes no rows and a Jaccard computed over inserted sets measures the deduplicating store rather than the system. That figure is retained in results.json under `reproducibility_inserted_sets` as a diagnostic only.

## Settings recorded for this run

```json
{
  "window_days": 90,
  "gold_set_path": "data/gold/labels.yaml",
  "n_signals": 3361,
  "n_runs": 261,
  "n_token_rows": 123
}
```
