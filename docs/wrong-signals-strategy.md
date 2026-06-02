# Wrong signals — how to find them, fix them, and prevent them

A wrong signal is one that should not be in `public.signals` as classified. Three kinds, each with a different cause and a different fix:

| Kind | Example | Cause | Fix |
|---|---|---|---|
| **Wrong attribution** | A press release names ETH Zurich in passing; signal attributes it to ETH Zurich. | Extractor over-attributes to mentioned actors. | Critic DROP RULE 1 (actor-relevance). Already tightened in v0.4.0. |
| **Off-topic** | A news article about classical HPC at CSCS gets attributed to a quantum actor. | Search returned a low-relevance hit; Classifier accepted it. | Critic DROP RULE 2 (quantum-relevance). Already tightened in v0.4.0. |
| **Wrong dimension** | A funding announcement classified as `awards` instead of `funding_event`. | Classifier picked the wrong sub-category. | Critic DROP RULE 3 (dimension-evidence match). Already tightened in v0.4.0. |

The v0.4.0 Critic addresses the **prevention** side for *new* signals. This doc covers **finding** and **correcting** existing wrong signals.

---

## Three workflows, ordered by effort

### Workflow A — Lightweight: SQL audit + manual delete (zero new code)

For the empirical-evaluation phase, this is enough. Run a few targeted SQL queries in the Supabase SQL editor to find suspect signals; delete the rows you don't want.

**Find generic-boilerplate suspects:**

```sql
select id, actor_slug, dimension, evidence_quote, source_url, inserted_at
  from public.signals
 where lower(evidence_quote) ~ '(leading provider|committed to|world-class|transforming|empower(ing)?|revolutionary)'
 order by inserted_at desc
 limit 50;
```

**Find signals where the actor doesn't appear in the evidence quote:**

```sql
select s.id, s.actor_slug, a.name, s.evidence_quote, s.source_url
  from public.signals s
  join public.actors a on a.slug = s.actor_slug
 where position(lower(a.name) in lower(s.evidence_quote)) = 0
   -- ETH/EPFL etc. often appear as abbreviations not full names. Tighten case-by-case.
 order by s.inserted_at desc
 limit 50;
```

**Find dimension/evidence mismatches** (e.g. `patents` dim with no patent-number-shaped string in the quote):

```sql
select id, actor_slug, dimension, evidence_quote
  from public.signals
 where dimension = 'patents'
   and evidence_quote !~ '\m([A-Z]{2}\s?\d{6,}|[A-Z]{2}\s?\d{4}/\d+|WO\d+|EP\d+|US\d+)'
 limit 50;
```

**Delete the confirmed-wrong rows:**

```sql
delete from public.signals where id in ('uuid-1', 'uuid-2', ...);
```

The `signals` table has an `audit_log` foreign-key cascade, so the delete is clean.

**Pros.** Zero code; immediate; gives you visibility into the kinds of errors that occur.
**Cons.** No record of *why* a signal was deleted; can't replay the decision; need to repeat after every fresh cron tick.

---

### Workflow B — Inline: "flag wrong" button on the website (medium effort, ~half-day)

Add a "Report" link next to each signal on the website. Clicking it adds the signal id to a new `signal_flags` table with a reason category (wrong-attribution / off-topic / wrong-dimension / low-quality). The cron then refuses to re-insert flagged-id signals on future runs.

**Schema delta:**

```sql
create table if not exists public.signal_flags (
    id          uuid primary key default gen_random_uuid(),
    signal_id   uuid not null references public.signals(id) on delete cascade,
    reason      text not null check (reason in (
        'wrong_actor', 'off_topic', 'wrong_dimension', 'low_quality', 'duplicate', 'other')),
    note        text,
    flagged_at  timestamptz not null default now()
);

-- Persistence checks against this set before re-inserting.
create index if not exists signal_flags_signal_idx on public.signal_flags (signal_id);
```

**API delta:**

```
POST /api/signal-flags  { signal_id, reason, note? }   → creates a flag
GET  /api/signal-flags?signal_id=...                    → lists flags for a signal
```

**Persistence delta:** before insert, query `signal_flags` and skip any candidate whose `(actor_slug, source_url, content_hash)` matches a flagged signal's tuple.

**Pros.** Audit trail. Once a signal is flagged, it stays out. Cheap to use during the daily review.
**Cons.** Requires API + frontend changes; one round-trip per flag.

---

### Workflow C — Heavyweight: re-classification endpoint (high effort, ~1 day)

`POST /api/signals/{id}/reclassify` re-runs the Classifier + Critic on a single signal (read original document from cache, re-prompt, write a new row). Useful for testing prompt changes against a specific known-bad signal without re-running the whole cron.

**Pros.** Closes the loop on prompt-engineering iterations. Lets the thesis report "fix rate" as a tuning metric.
**Cons.** Requires raw document persistence beyond the audit folder; LLM cost per call; only useful if you're actively iterating on prompts.

---

## Recommendation

**Adopt Workflow A immediately**, while the cron is running daily and the corpus is small. It's a 5-minute SQL session per week.

**Add Workflow B in week 2 of the empirical evaluation phase** (~ 2026-06-09 onwards), when the daily corpus stabilises and you want to review systematically. The `signal_flags` table also becomes a useful artefact: the thesis can report "X% of cron-generated signals were human-flagged as wrong post-hoc" as a *quality* metric.

**Skip Workflow C unless the prompts are still in flux.** Once the Critic prompt stabilises, single-signal reclassification is not worth the engineering.

---

## What the v0.4.0 Critic already does for *new* signals

The Critic in [`systems/masfactory/masfactory_system/agents/critic.py`](../systems/masfactory/masfactory_system/agents/critic.py) is now strict. From the prompt:

> DROP RULES (apply in order — drop on the FIRST hit):
>
> 1. ACTOR-RELEVANCE. The evidence_quote must unambiguously concern the actor named by actor_slug. Drop if mentioned only in passing / in a long list / in a footnote.
> 2. QUANTUM-RELEVANCE. The evidence_quote must concern quantum technology. Drop if about non-quantum work.
> 3. DIMENSION-EVIDENCE MATCH. Per-dimension specifics (patents need a patent number, publications need a paper title/venue, funding needs an amount/investor, etc.).
> 4. CONFIDENCE THRESHOLD ≥ 0.45.
> 5. BOILERPLATE drops ("leading provider", "we are committed to", positioning statements with no specifics).
> 6. DUPLICATES including cross-source (news + press of same event).

Combined with the optional consensus Critic (`MASF_CRITIC_CONSENSUS_PASSES=3`) and debate Critic (`MASF_CRITIC_DEBATE_ROUNDS=1`), the prevention layer is as strong as the architecture permits. The two layers together mean: the wrong-signals problem will diminish over time, even before Workflow B ships.

---

## Reporting wrong signals as a thesis metric

A natural by-product of Workflow B is the **wrong-signal rate** — flags ÷ persisted signals — broken down by:

- Actor category (private companies vs research institutes)
- Signal type (legitimacy / customer_cocreation / community_ecosystem / future_trajectory)
- Source (arxiv / website / news / press / patents)
- System (A vs B)

This becomes a directly-comparable quality metric for the cross-system comparison in Chapter 3.5. Recommend including it.
