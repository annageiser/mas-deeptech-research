# Methodology — how this skeleton instantiates the constructive research approach

The thesis follows the **constructive research approach** (Kasanen, Lukka & Siitonen, 1993), which is appropriate when the goal is to build an artefact that addresses a real-world problem and to evaluate how well it does so. This document records *how* the choices in this codebase map onto the methodology described in the disposition.

## Two-step validation

| Stage | What the disposition says | Where it lives in this repo |
| --- | --- | --- |
| 1 — Theoretical validation | Derivation of an ideal reference architecture from a systematic literature review. Both candidate implementations are mapped onto this ideal to identify which choices each one realises and which it omits. | Tracked in the thesis document; the *gap analysis* will reference specific nodes and decisions in [`docs/architecture.md`](architecture.md). |
| 2 — Empirical validation | Two parallel artefacts run on the same task on the Swiss-quantum ecosystem; cross-system comparison on classification quality, output quality per token cost, reproducibility. | System A lives in [`systems/masfactory/`](../systems/masfactory). System B will live in `systems/hermes/`. Shared evaluation in [`evaluation/`](../evaluation). |

## Reproducibility "designed in, not rebuilt"

The disposition (§Research Methods → *Constructive development*) commits to having reproducibility infrastructure ready *before* either system is built. The artefacts here that honour that commitment:

- **Pinned dependencies** — `masfactory==1.0.3` and a fixed Python image (`python:3.11-slim`).
- **Versioned prompts** — all prompts live in `systems/masfactory/masfactory_system/agents/*.py` next to the node they belong to, so a `git log -p systems/masfactory/masfactory_system/agents/extractor.py` answers "what was the prompt on date X?".
- **Per-run audit trail** — every `g.invoke()` creates `data/raw/runs/<iso-ts>/` containing the raw config, classifications, critique, surviving signals, and the markdown brief. The directory is bind-mounted from the host so it survives container rebuilds.
- **Per-node token tally** — written to Supabase `token_usage` (one row per node per run) and to the same audit folder. This is the primary input for the "output quality per token cost" evaluation.
- **Docker-on-VPS** — the same image runs identically on any Hostinger VPS with the same `.env`. The `RUN python -m masfactory_system.runner build-check` step in the Dockerfile means a broken graph never reaches the VPS.

## Build–evaluate–refine cycles

The graph in `masfactory_system/graph.py` is explicitly linear and short (7 nodes). That makes a single B–E–R cycle cheap:

1. Edit one node's prompt or implementation.
2. `docker compose build masfactory` (rebuild + smoke check, ~1 min).
3. `docker compose run --rm masfactory run-once --limit-actors 2` (small batch, ~2 min).
4. Inspect the new audit folder and the Supabase rows.

The triweekly supervisor reviews should bring at most two prompt or schema changes between reviews — anything larger should escalate to a graph-shape change (new node), which is what the architecture-gap analysis is *for*.

## What this skeleton deliberately defers

The disposition's evaluation depends on the *gap* between the ideal architecture and what's built. To make that gap honest, these things are intentionally *not* in v1 — they are the obvious "ideal" components the thesis can either later add or document as omitted-with-reason:

- Embeddings on the `signals.embedding` column (Critic dedup currently relies on `evidence_quote` heuristics).
- Swissreg patent ingestion (collector stub left in; `source_kind='swissreg'` reserved in schema).
- Streamlit dashboard (milestone M7; the data is already structured enough to build it).
- Hub graph variant where multiple Extractors / Classifiers run in parallel (current Linear graph keeps token cost minimal; the *ideal* MAS architecture from the literature has parallelism).
- Loop-based "discuss until consensus" critic (the architecture diagram does not include a loop; if the literature review pushes for one, this is a small graph change).
