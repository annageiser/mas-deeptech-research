---
name: parallel-cli
description: Sequence multiple data-gathering tool calls for a single actor efficiently.
version: 0.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [orchestration, swiss-quantum]
    category: meta
---

# When to use

Always — this skill describes the order in which the AIAgent should call the
data-gathering tools for one actor.

# Procedure

For each actor, the agent should follow this sequence to spend its iteration
budget well:

1. **arXiv first** (cheapest, structured): `arxiv_search` once.
2. **Website second** (one fetch, robots-aware): `website_fetch` for the
   homepage. Skip if the actor has no homepage.
3. **Classification + registration**: call `register_signal` for each piece
   of evidence found across the two sources.
4. **Finish**: call `finish_actor` with a 3–5 line markdown brief listing the
   top 2 signals.

The agent has a small budget per actor (`HRM_MAX_ITERATIONS`, default 6).
Steps 1–2 should consume at most 2 iterations; the remaining iterations are
for `register_signal` and `finish_actor`.

# Pitfalls

- Do not call the same tool twice with the same args — the LLM is
  occasionally tempted to retry. The Tools Registry does not deduplicate.
- Do not exceed `max_pages=1` on the website fetch — additional pages rarely
  add signal and burn the iteration budget.
- Never skip `finish_actor` — without it the audit folder will mark the run
  as `max_iterations` (degraded).

# Verification

Inspecting the audit folder's `actor_<slug>.json` should show
`iterations_used ≤ 6` and `stopped_reason = "finish"` for a healthy run.
