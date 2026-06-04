# Feature candidates — GitHub research for BOTH systems

Catalogue of existing open-source projects whose features could be integrated into MASFactory (System A) or Hermes (System B). For each: source, function, integration effort, and which system it fits.

Updated whenever Anna or the assistant discovers a relevant project during research. The thesis cites this list as part of the gap-analysis chapter (where the literature points to capabilities that *could* be added but weren't, with the rationale documented here).

---

## Discovery infrastructure

### `feedparser` (already integrated)
- **Source:** https://github.com/kurtmckee/feedparser
- **Function:** Atom / RSS / RDF feed parsing.
- **Used in:** both systems' `collectors.py` and the new `collection/rss.py`.
- **Integration effort:** done.

### `python-feedgen` (candidate)
- **Source:** https://github.com/lkiesow/python-feedgen
- **Function:** Generate Atom/RSS feeds (the inverse of feedparser).
- **Use case:** the weekly thesis report could publish itself as an RSS feed Anna's supervisor can subscribe to.
- **Effort:** ~half-day. Useful but not critical.
- **Fits:** Container C (reports), not the MAS systems.

### `news-please` (candidate)
- **Source:** https://github.com/fhamborg/news-please
- **Function:** Open-source news crawler with built-in extraction. Handles paywalls + canonical URLs + duplicate detection out of the box.
- **Use case:** broader news collection beyond Google News / Bing News — drop-in replacement for `collection/news.py` if we hit Bing rate limits.
- **Effort:** ~1 day. Higher dependency surface but much richer extraction.
- **Fits:** both systems.

---

## Classification / coding

### `simpletransformers` / `transformers` zero-shot classification (candidate)
- **Source:** https://github.com/huggingface/transformers
- **Function:** Local zero-shot classifier as an alternative / supplement to the LLM Classifier. Lower cost per signal, deterministic, easier to evaluate.
- **Use case:** parallel run alongside the LLM Classifier; comparison becomes a real A/B (zero-shot transformer vs LLM prompt-based) in Chapter 4.
- **Effort:** ~2 days. Includes downloading a 500MB model into the container image.
- **Fits:** both systems as an optional capability layer (env-gated).

### `Atlas.ti API` (manual)
- **Source:** https://atlasti.com
- **Function:** Anna's manual coding tool. Has a Python API for read access to coded segments.
- **Use case:** read Anna's manually coded segments + ingest into `signal_flags` (`correct_example`) and `missed_signals`.
- **Effort:** depends on Anna's chosen format. Documented in [`open-questions.md`](open-questions.md) as a decision point.

### `QualCoder` (alternative manual tool)
- **Source:** https://github.com/ccbogel/QualCoder
- **Function:** Open-source qualitative-coding GUI. SQLite backend means easy programmatic export.
- **Use case:** same as Atlas.ti above — Anna picks one or the other.
- **Effort:** depends on Anna's choice.

---

## Knowledge graph

### `networkx` + `pyvis` (already integrated)
- **Source:** https://github.com/networkx/networkx + https://github.com/WestHealth/pyvis
- **Function:** Graph algorithms + interactive visualisation.
- **Used in:** the legacy Streamlit dashboard's graph page.
- **Status:** the new Next.js dashboard renders a dependency-free SVG instead — see [`how-the-systems-work.md`](how-the-systems-work.md). The legacy is kept transitional.

### `cytoscape.js` (candidate, dropped)
- **Source:** https://github.com/cytoscape/cytoscape.js
- **Function:** Mature web-graph rendering library.
- **Considered for:** the v0.4.0 knowledge-graph redesign.
- **Status:** **rejected.** The dependency-free SVG approach in `GraphCanvas.tsx` covers our 30-actor case without an extra ~400KB JS bundle. Cytoscape would be the natural next step at > 200 actors.

---

## Agent infrastructure

### `langchain` agent toolkit (candidate, not adopted)
- **Source:** https://github.com/langchain-ai/langchain
- **Function:** Broad agent framework with tool / memory / RAG plumbing.
- **Considered for:** Hermes-style System B before MASFactory was chosen.
- **Status:** **rejected** in favour of MASFactory (System A) for orchestration and a hand-rolled Hermes-pattern AIAgent (System B). LangChain's abstractions felt too heavy for the comparative-evaluation goal — we wanted the two systems' code to be readable end-to-end for the thesis audit.

### `instructor` (candidate)
- **Source:** https://github.com/jxnl/instructor
- **Function:** Pydantic-validated LLM outputs — automatically retries / repairs malformed JSON.
- **Use case:** wraps OpenRouter calls in both systems so the "200 OK no choices" / "garbled JSON" failure modes self-heal instead of bubbling to the failover model.
- **Effort:** ~half-day per system. Real win for reliability.
- **Fits:** both systems, env-gated as `MASF_USE_INSTRUCTOR=1`.

### `dspy` (candidate)
- **Source:** https://github.com/stanfordnlp/dspy
- **Function:** Self-optimising prompts — instead of hand-writing the Classifier prompt, DSPy learns it from a few-shot gold set.
- **Use case:** once Anna's parallel coding produces ≥ 50 gold examples, DSPy could replace the static Classifier prompt with one tuned against her labels. Empirical: their paper claims 40-60% accuracy lift vs prompt engineering.
- **Effort:** ~2 days. Real thesis contribution if it works.
- **Fits:** System A; not natural for Hermes (which doesn't have a single classification step).

---

## Evaluation / observability

### `evidently` (candidate)
- **Source:** https://github.com/evidentlyai/evidently
- **Function:** ML-monitoring library — drift detection, prediction-quality reports.
- **Use case:** track classifier-quality drift over the cron's calendar life. Would replace some of `systems/evaluation/`'s by-hand reporting.
- **Effort:** ~1 day. Adds a ~50MB dep.
- **Fits:** add to `systems/evaluation/`.

---

## How to use this list

When the assistant adds a candidate, fill all five fields. When Anna adopts one, move it to the "already integrated" sub-section. When she rejects one, note the rationale.

The thesis's Chapter 4 (gap analysis) cites this list as the "what an ideal architecture might also include" rubric.
