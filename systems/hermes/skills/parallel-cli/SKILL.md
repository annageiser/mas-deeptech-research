---
name: parallel-cli
description: Sequence multiple data-gathering tool calls for a single actor efficiently.
version: 0.2.0
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

1. **arXiv first** (cheapest, structured): `arxiv_search` once with the
   actor's name or `arxiv_query`.
2. **Website second** (one fetch, robots-aware): `website_fetch` for the
   homepage. Skip if the actor has no homepage. The fetch now also
   discovers RSS feeds + newsy subpages, so a single call typically
   returns several distinct article URLs.
3. **News third** (third-party coverage): `news_search` with the actor's
   display name. Pulls Switzerland-biased Google News results — gives the
   non-actor-controlled viewpoint the supervisor cares about
   (Kolbe & Burnett 1991 content-analysis methodology).
4. **Classification + registration**: call `register_signal` for each piece
   of evidence found across the three sources. Use `source_kind` =
   `"arxiv"`, `"website"`, or `"news"` to match where the evidence came
   from.
5. **Finish**: call `finish_actor` with a 3–5 line markdown brief listing
   the top 2 signals.

The agent has a small budget per actor (`HRM_MAX_ITERATIONS`, default 6).
Steps 1–3 should consume at most 3 iterations; the remaining iterations
are for `register_signal` and `finish_actor`.

# Pitfalls

- Do not call the same tool twice with the same args — the LLM is
  occasionally tempted to retry. The Tools Registry does not deduplicate.
- Do not exceed `max_pages=1` on the website fetch — additional pages
  rarely add signal and burn the iteration budget.
- Pass the actor's *display name* to `news_search`, not the slug. Google
  News matches better on real names.
- Always tag signals from `news_search` with `source_kind="news"`. Mixing
  source kinds in the database breaks the dashboard's per-source filters.
- Never skip `finish_actor` — without it the audit folder will mark the
  run as `max_iterations` (degraded).

# Verification

Inspecting the audit folder's `actor_<slug>.json` should show
`iterations_used ≤ 6` and `stopped_reason = "finish"` for a healthy run.
The Supabase `signals` table should contain rows with at least two
distinct `source_kind` values for actors that yielded signals.
