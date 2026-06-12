# System A vs System B — technology stack comparison

Side-by-side audit of every external service / library / model the two systems use, with notes on cost, parity, and recommendations.

**Working principle**: the thesis is a **comparative study of two MAS architectures**. The two systems SHOULD differ in *architecture* (graph vs single-loop) — that's the whole point. They should NOT differ in *infrastructure* (model, vector DB, schema) any more than necessary, because that turns the comparison into a confounded mess. This document lists where the two stacks line up, where they don't, and where the divergence is justified vs accidental.

## Layer-by-layer audit

| Layer | System A (MASFactory) | System B (Hermes) | Same? | Cost |
|---|---|---|---|---|
| **Primary LLM** | `nvidia/nemotron-3-super-120b-a12b:free` | `nvidia/nemotron-3-super-120b-a12b:free` | ✅ Yes (since v0.4.10) | $0 / unlimited |
| **Fallback LLM** | `meta-llama/llama-3.3-70b-instruct:free` (in MASF_MODEL_FALLBACK) | n/a (Hermes uses its own retry) | ~ Different, both `:free` | $0 |
| **Auxiliary LLM paths** | (none — single model end-to-end) | `meta-llama/llama-3.3-70b-instruct:free` for vision/web_extract/session_search/compression (v0.4.8 lockdown) | ~ Different, both `:free` | $0 |
| **LLM gateway** | OpenRouter | OpenRouter | ✅ Yes | $0 / requires ≥$0 balance for credit-hold pre-auth |
| **Web search backend** | `httpx` + Google News / Bing News RSS + arXiv API + EPO OPS | `ddgs` (DuckDuckGo, v0.4.14) + optional Firecrawl (paid tier) | ❌ Different (architectural — see below) | $0 (ddgs) |
| **Web extraction** | `selectolax` parser on raw HTML | Snippet-only via ddgs (or full-page via Firecrawl when key present) | ❌ Different | $0 with ddgs |
| **Patent collection** | EPO Open Patent Services (OAuth2, free tier) | none currently | ❌ A-only | $0 (OAuth + free tier) |
| **RSS** | `feedparser` reading `data/raw/rss_feeds.yaml` (industry + swiss_media + vendor + defense feeds) | upstream `blogwatcher` skill (v0.4.18) | ~ Different (same data spirit, different tool) | $0 |
| **Embeddings** | `fastembed` + `BAAI/bge-base-en-v1.5` (768d, ONNX, ~210MB) — gated by `MASF_EMBEDDINGS=1` | not currently used | ❌ A-only | $0 (local model) |
| **Vector DB** | Supabase pgvector | n/a | ❌ A-only | $0 (included with Supabase) |
| **Relational DB** | Supabase Postgres | Supabase Postgres (same instance, same schema) | ✅ Yes | Free tier 500 MB, well within bounds |
| **Memory across runs** | none (stateless cron) | upstream Hermes memory (sqlite-like, in $HERMES_HOME/memory/) | ❌ B-only | $0 |
| **Skills loader** | inline prompts in agent classes | upstream Hermes loads `~/.hermes/skills/*/SKILL.md` (75 bundled + 1 ours) | ❌ Different by design | $0 |
| **MAS framework** | `masfactory==1.0.3` (pinned, ~3 KB Python wrapper around dataclass + dict) | upstream NousResearch hermes-agent (~317 MB, ~3,500 source files) | ❌ Different by design (THIS IS THE THESIS COMPARISON) | n/a |
| **Container base** | `python:3.11-slim` (~150 MB) | Debian 13 + Node 22 + Playwright + s6-overlay + uv (~4.65 GB image after upstream build) | ❌ Different | $0 |
| **Web frontend** | (shared — `systems/web` Next.js + `systems/api` FastAPI) | (shared) | ✅ Yes | $0 |
| **Reverse proxy + TLS** | Caddy 2.10 (shared) | Caddy 2.10 (shared) | ✅ Yes | $0 |
| **VPS** | Hostinger srv1684595 (shared) | Hostinger (shared) | ✅ Yes | ~$8/mo (Hostinger plan) |

## Where the divergences are intentional (and should stay)

These are the differences that **make the thesis interesting**. Don't unify them:

1. **MAS framework itself** (MASFactory graph vs Hermes single-loop). The whole thesis comparison hinges on this.
2. **Skills surface** (inline prompts vs `SKILL.md` files). This is "agent architecture, hard-coded prompts" vs "agent architecture, swappable skills".
3. **Persistence pattern** (stateless cron vs persistent memory). System A reads Supabase as the only state; System B accumulates internal memory across cron runs.
4. **Container footprint** (150 MB vs 4.65 GB). This is a direct comparison axis: deployment cost vs feature surface.

## Where the divergences are accidental and could be fixed

These are leaks of architecture into infrastructure. Worth closing:

### 1. System B has no embeddings ⇒ no semantic dedup ⇒ comparison numbers are confounded

System A's `MASF_SEMANTIC_DEDUP=1` (when enabled) drops signals whose embeddings are within 0.92 cosine of an existing signal. System B has no embedding step, so every signal that gets through the Ehrenthal classification lands. **This biases the comparison toward "B has more signals than A"** — but it's because A is deduping and B isn't.

**Fix**: add a small embedding step to `persist_signals.py` (Hermes wrapper). Use the same `BAAI/bge-base-en-v1.5` via `fastembed` so cross-system embeddings live in the same space. Gate behind `HRM_EMBEDDINGS=1` like the MASFactory env var. Then `HRM_SEMANTIC_DEDUP=1` reuses the existing Postgres `find_similar_signals` RPC. **Cost: $0** — `fastembed` is local CPU. **Image impact**: +210 MB to Hermes wrapper layer.

**Acceptance task**: M.1 in the backlog (task #113) — turn semantic dedup on. The embedding pass for B is a prerequisite. *Tracked as v0.4.20 candidate work.*

### 2. System A doesn't surface bundled domain skills

Hermes has 75 bundled skills (`arxiv`, `blogwatcher`, `company-research`, etc.) — we activated 4 of them in `--skills`. System A has bespoke collectors hand-written in `collection/*.py`. Some of B's bundled skills (specifically `arxiv` and `blogwatcher`) replicate what A already does, but in a different style.

**Recommendation**: don't unify. The point of B is that the skills are pluggable. Keep A's hand-written collectors and B's plug-in skills as the comparison axis. Document this divergence in the methodology.

### 3. System A still has the legacy `defense_signals` in `classification/schema.yaml`

v0.4.19 moved defense to boolean flags everywhere except System A's classification YAML. Task #123 cleans it up. **No cost impact.** This is a methodology drift that should close before the empirical-evaluation window.

### 4. Firecrawl is still configurable in `.env.example` for System B

Anna's free-only policy says: no paid services. Firecrawl's free tier is 500 credits/month. After the first cron + smoke days, this depletes; then ddgs takes over. Cleaner: drop Firecrawl from `.env.example` entirely so newcomers don't accidentally activate it. v0.4.19 left it commented; v0.4.20 could remove it. **Already a documented preference (Bug 4); doesn't need a code change unless we want zero risk of activation.**

## Other technology worth considering

Things that would benefit the thesis without breaking the free-only constraint:

### A — Phoenix (open source, by Arize) — observability

What it does: collects every LLM call's prompt + response + tokens + latency into a queryable SQLite DB. Replaces the current Supabase `token_usage` instrumentation with something that gives you per-call drill-down for the lessons-learned chapter.

Why I'd suggest it: when you write Chapter 4.1.4 (threats to validity), being able to *replay* any specific signal's full prompt history (which model? which system prompt version? which auxiliary calls?) saves hours over reconstructing from logs.

Cost: $0 (local SQLite). Image impact: ~50 MB Python package.

How to introduce: a single decorator on the OpenRouter wrapper in `systems/masfactory/.../model.py` and on `persist_signals.py`'s Hermes invocation. Both systems write to the same Phoenix DB; you can filter by system in the UI. Optional layer; gate behind `PHOENIX_ENABLED=1`.

### B — `litellm` as the LLM gateway abstraction

What it does: wraps every OpenRouter / Anthropic / etc. provider in one Python API. Lets you swap providers per-request.

Why I'd suggest it: when the supervisor inevitably asks "what if you used Claude 3.5 Sonnet instead?" — you can change one env var, not edit 5 agent files. Plus litellm has built-in retry, fallback, and cost-tracking that we're hand-rolling in `FailoverLegacyOpenAIModel`.

Cost: $0. Image impact: ~10 MB.

Trade-off: introduces another dependency. Not strictly necessary; OpenRouter's free models work fine. Defer unless the supervisor pushes "test multiple models" before the thesis defence.

### C — `tavily-python` instead of `ddgs` for B's web tool

What it does: same role as ddgs (web_search backend), but Tavily returns AI-tuned snippets with higher relevance for fact extraction. Free tier: 1,000 credits/month.

Why I'd suggest it: ddgs has been throttling Hermes-style cron-burst usage in the wild (DuckDuckGo's parent company has tightened bot detection in 2026). Tavily is more reliable for batch workloads.

Cost: $0 at the free tier (40 actors × ~3 searches/run × daily = 3,600/mo — exceeds Tavily's 1k/mo. **Would require weekly cron, not daily.**)

Verdict: **don't switch** unless ddgs throttles. Keep Tavily as a documented fallback in the `.env.example`. If you ever see "0 signals across all actors with ddgs errors in stderr" — that's the signal to switch.

### D — `instructor` for structured-output discipline on System A

What it does: validates LLM JSON outputs against a Pydantic schema *automatically* — if the model produces malformed JSON, `instructor` retries with the validation error appended to the prompt.

Why I'd suggest it: System A's `Classifier` currently relies on string parsing of the LLM's JSON; we hit "model output is markdown-fenced JSON, not raw" bugs more than once. `instructor` handles this gracefully.

Cost: $0. Image impact: ~3 MB.

How to introduce: thin wrapper around the existing `LegacyOpenAIModel` calls in `classifier.py` and `critic.py`. Hermes already does something similar internally — adopting `instructor` on A would close another infrastructure gap.

### E — `BAAI/bge-reranker-base` for the Critic (System A)

What it does: a small (110 MB) cross-encoder model that scores `(query, document)` pairs. Run in CPU via fastembed.

Why I'd suggest it: System A's Critic uses an LLM call to decide keep/drop. A cross-encoder reranker score (0-1) is much faster and 100% local. Adopting it would let the Critic do a *first-pass filter* (drop everything below score 0.3) before the LLM-call critique runs on the survivors. Reduces LLM token cost significantly.

Cost: $0. Image impact: +110 MB to MASFactory image.

Trade-off: changes Critic semantics. Worth A/B-testing in the evaluation chapter.

## Recommendations — ranked

| Order | Action | Cost | Time |
|---|---|---|---|
| 1 | **M.1 + B-embeddings** (task #113 + new) — turn semantic dedup on for A, add embedding pass to B so the dedup applies to B too. Removes a real comparison confound. | $0 | ~3 h |
| 2 | **#123 schema.yaml cleanup** — finish the v0.4.19 refactor on A's classification YAML. | $0 | ~1 h |
| 3 | **Phoenix observability** — adds replay-able LLM-call log for the thesis lessons-learned chapter. | $0 | ~2 h |
| 4 | **`instructor` on System A** — close another infrastructure leak; reduces "JSON parsing surprise" bugs. | $0 | ~2 h |
| 5 | **Drop `FIRECRAWL_API_KEY` from `.env.example`** entirely; document ddgs as the only supported B backend. | $0 | ~10 min |
| (Defer) | `litellm`, Tavily, bge-reranker — only if specific supervisor questions or production-load issues surface. | $0 | n/a |

Everything above stays **inside the $0 envelope**. Nothing introduces a paid service, a token-billable model, or a runtime dependency on a SaaS that could change pricing.

Recommendation 1 is the most thesis-defensible — it eliminates a confound that would otherwise need a paragraph in threats-to-validity. Recommendation 3 is the highest-leverage for the writing-up phase. Both can land in v0.4.20.
