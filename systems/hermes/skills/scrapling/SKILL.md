---
name: scrapling
description: Lightweight, robots-aware fetch of an actor website page and signal extraction.
version: 0.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [scraping, web, swiss-quantum]
    category: research
---

# When to use

Use when the actor has a `homepage` URL — every actor in `actors.yaml` except
a small handful does. Useful for non-technical signals (announcements,
partnerships, hires, market positioning) that don't appear on arXiv.

# Procedure

1. Call `website_fetch` with `url = actor.homepage` and `max_pages = 1`.
2. From the returned visible text, look for *concrete* claims:
   - new product / capability announcements
   - named partners or customers
   - funding or grant amounts
   - leadership / advisor names
   - roadmap statements with dates
3. For each, call `register_signal`:
   - Pick the dimension that matches (often `partnership_or_alliance`,
     `funding_or_grant`, `market_positioning`, `hiring_or_talent`).
   - `is_technical = false` for most of these; `true` only if the page
     describes hardware/software specifics.
   - `confidence ≈ 0.5–0.7` — homepages have marketing language; weight quotes
     that contain numbers or names higher.
   - `evidence_quote` must be verbatim. If you can't find a quote that
     supports the signal, drop it.

# Pitfalls

- Homepages change. Don't rely on positional cues ("the third paragraph
  says"); search by keyword.
- Many sites are bilingual (DE/FR/EN). Take whichever language is clearest;
  don't translate.
- If the homepage is mostly JS-rendered, the fetched text may be sparse —
  that's expected, just register fewer signals.

# Verification

Each registered signal's `evidence_quote` should be locatable on the page
with Ctrl-F.
