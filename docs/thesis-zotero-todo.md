# Zotero TODO — references that the thesis body now cites but that aren't in the Zotero library yet

**Date:** 2026-06-29
**Why this file exists:** The `References` section in `Bachelor_Thesis_Geiser_Anna.docx` is currently empty — Zotero populates it on refresh from the in-text citation fields in the body. The body of the thesis now cites four works that almost certainly are NOT in your Zotero library yet (and one in-text citation that pointed at the wrong author and was just corrected). Add the four below to Zotero, then mark each existing plain-text citation in the body as a Zotero citation, then run **Document Preferences → Refresh** in the Zotero Word plugin.

## 1. Add these four works to Zotero (copy-paste-ready APA entries)

```
Curtain, C., & Salomón, K. (2026). QualCoder (Version 3.6) [Computer software]. https://github.com/ccbogel/QualCoder

Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). Improving factuality and reasoning in language models through multiagent debate (arXiv:2305.14325). arXiv. https://doi.org/10.48550/arXiv.2305.14325

Hutto, C. J., & Gilbert, E. (2014). VADER: A parsimonious rule-based model for sentiment analysis of social media text. Proceedings of the International AAAI Conference on Web and Social Media, 8(1), 216–225. https://doi.org/10.1609/icwsm.v8i1.14550

Wang, X., Wei, J., Schuurmans, D., Le, Q. V., Chi, E. H., Narang, S., Chowdhery, A., & Zhou, D. (2023). Self-consistency improves chain of thought reasoning in language models (arXiv:2203.11171). arXiv. https://doi.org/10.48550/arXiv.2203.11171
```

(If the QualCoder author names differ on the repository's `AUTHORS.md` at submission time, use that.)

## 2. Bind the in-text citations to the new Zotero entries

After adding the four works above to Zotero, find each plain-text citation in the .docx and **convert it to a Zotero citation** by selecting the citation text and clicking *Add/Edit Citation* in the Zotero Word plugin — then pick the matching Zotero entry from the search box.

| Citation in body | Section(s) where it appears | Zotero entry to link |
|---|---|---|
| `(Hutto & Gilbert, 2014)` | §2.2.4 (evaluation framework), §3.3 (three subsystem-level design choices) | Hutto & Gilbert (2014) — VADER |
| `(Wang et al., 2023)` | §2.1.5 (Critic component) | Wang et al. (2023) — Self-consistency |
| `(Du et al., 2023)` | §2.1.5 (Critic component), §3.3 (Critic description), §3.6 (gap-analysis table row for Critic) | Du et al. (2023) — Multi-agent debate |
| `(Curtain & Salomón, 2026)` | §2.1.3 (content-analysis lineage), §2.2.4 (gold-standard protocol) | Curtain & Salomón (2026) — QualCoder |

The §2.1.3 and §2.2.4 QualCoder citations were corrected from the previous (incorrect) "Bogel, n.d." attribution on 2026-06-29 — this matches the actual upstream maintainership on the QualCoder GitHub repository.

## 3. Refresh Zotero

In Word: *Document Preferences → Refresh*. The References section at the back of the .docx will populate with every cited work in alphabetical order.

## 4. Sanity-check pass

After the refresh, every Zotero-managed reference list entry should match an in-text citation, and every in-text citation should resolve to a reference list entry. If Zotero reports unresolved citations, the unbound plain-text citations are flagged in the right-hand "Document Citations" panel.

If Zotero ever fails to find an existing entry by author-year, the in-text citation will render as a yellow `(Author, n.d.)` placeholder — that is the visible signal that the bind step was missed for that citation.
