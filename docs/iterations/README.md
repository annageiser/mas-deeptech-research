# Iterations log

Per the constructive-research methodology (Kasanen, Lukka & Siitonen 1993), every meaningful build-evaluate-refine cycle gets its own short entry here. Format borrowed from the to-do brief: **Problem · Under the Hood · Next Steps.**

Each entry is one Markdown file named `vX.Y.Z-short-title.md`. Git commits in the cycle are tagged with the same version so the entries can be cross-referenced to the diff.

| Version | Date | Title | Highlight |
|---|---|---|---|
| [v0.4.2](v0.4.2-defense-signals-rss-labelling.md) | 2026-06-02 | Defense signals + RSS + Anna's labelling | 5th signal_type · feed-discovery layer · gold-example labelling for few-shot |
| (v0.4.1) | 2026-06-02 | arXiv author-affiliation fix | covered in `docs/signal-collection-expansion-plan.md` |
| (v0.4.0) | 2026-06-01 | Ehrenthal four-signal scheme | covered in `docs/signal-taxonomy.md` |

Earlier versions (v0.3.x, v0.2.x, v0.1.x) predate this iteration log; see [`docs/session_log.md`](../session_log.md) for the chronological record.

## How to add a new entry

1. Pick the next semver number — typically bump the patch unless the change is structural.
2. Copy [`_template.md`](_template.md) → `vX.Y.Z-short-title.md`.
3. Fill the three sections.
4. Tag the final commit of the iteration with `git tag vX.Y.Z` and push.
5. Add a row to the table above.
