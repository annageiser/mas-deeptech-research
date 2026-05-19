---
name: arxiv
description: Search arXiv for recent papers attributable to a Swiss-quantum actor and turn them into signals.
version: 0.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [research, paper, swiss-quantum]
    category: research
---

# When to use

Use this whenever the actor has a non-empty `arxiv_query` or is a university,
research institute, or company likely to have arXiv-indexed output.

# Procedure

1. Call `arxiv_search` with `query = actor.arxiv_query or actor.name` and a small
   `max_results` (3–8). Larger queries waste tokens.
2. For each returned entry:
   - Skip purely review / textbook entries unless they're explicitly the actor's.
   - Identify the most informative sentence in the abstract.
   - Call `register_signal` with:
     - `dimension = "research_output"` (or `"technical_capability"` if the entry
       explicitly describes a new device / hardware result)
     - `is_technical = true`
     - `confidence ≈ 0.7` for clear matches, lower for ambiguous affiliation
     - `evidence_quote` = the verbatim sentence (do not paraphrase)
3. If you find nothing useful, do not register any signals — just move on.

# Pitfalls

- arXiv affiliation strings are inconsistent. Be conservative about claiming
  authorship — if the affiliation isn't clearly the actor, drop confidence.
- Some actors have generic names (e.g. "Miraex"); rely on the abstract content
  to confirm relevance.

# Verification

A successful run produces ≥ 1 signal with `source_kind="arxiv"` and a quote
that an evaluator can find in the abstract at the registered `source_url`.
