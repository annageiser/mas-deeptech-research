# Supabase migrations

The container does **not** auto-migrate at startup (a cron-triggered runner must never have DDL side effects). This file collects every schema change since the initial deployment so you can paste them into the Supabase SQL editor in order.

All snippets are **idempotent** — safe to re-run.

---

## 2026-05-21 — initial schema

Source: [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql).

Paste the entire file once in the Supabase SQL editor. Creates `actors`, `runs`, `signals`, `token_usage`, `audit_log` + grants `service_role`. *Already applied on the current Supabase project; listed here for new deployments.*

---

## 2026-05-21 — `token_usage.calls` column + service_role grants

Applied during the initial go-live session — already in the canonical `schema.sql`. Listed here for a from-scratch deployment.

---

## 2026-05-25 — `signals.system` denormalised column

Applied during the go-live as a one-off ALTER. Already canonical in `schema.sql`. Listed here for a from-scratch deployment.

---

## 2026-05-25 (evening) — `source_kind = 'news'`

Adds the Google News source kind to the `signals.source_kind` CHECK constraint. Required after pulling commit `6162819` or later — otherwise `INSERT`s with the new source kind will be rejected with `value violates check constraint "signals_source_kind_check"`.

**Paste this into the Supabase SQL editor and Run:**

```sql
do $$
begin
    if exists (
        select 1 from pg_constraint
        where conname = 'signals_source_kind_check'
          and conrelid = 'public.signals'::regclass
          and not pg_get_constraintdef(oid) ilike '%news%'
    ) then
        alter table public.signals drop constraint signals_source_kind_check;
        alter table public.signals add constraint signals_source_kind_check
            check (source_kind in ('arxiv', 'website', 'swissreg', 'manual', 'news'));
    end if;
end $$;
```

**Verify:**

```sql
select pg_get_constraintdef(oid)
  from pg_constraint
 where conname = 'signals_source_kind_check';
```

Expected output contains `'news'`.

---

## 2026-05-31 — `find_similar_signals` RPC for semantic dedup

Adds the Postgres function the persistence layer calls when semantic dedup
is enabled (`MASF_SEMANTIC_DEDUP=1` / `HRM_SEMANTIC_DEDUP=1`). Required
after pulling commit `f013cf5` or later; without it, enabling dedup will
log warnings and degrade gracefully (no dedup, no crash) but the function
won't exist.

**Paste this into the Supabase SQL editor and Run:**

```sql
create or replace function public.find_similar_signals(
    p_actor_slug text,
    p_query_embedding vector(768),
    p_days_back integer default 30,
    p_limit integer default 1
)
returns table (
    id uuid,
    title text,
    evidence_quote text,
    source_url text,
    system text,
    similarity double precision,
    inserted_at timestamptz
)
language sql
stable
as $$
    select s.id,
           s.title,
           s.evidence_quote,
           s.source_url,
           s.system,
           1 - (s.embedding <=> p_query_embedding)::double precision as similarity,
           s.inserted_at
    from public.signals s
    where s.actor_slug = p_actor_slug
      and s.embedding is not null
      and s.inserted_at > now() - (p_days_back || ' days')::interval
    order by s.embedding <=> p_query_embedding asc
    limit greatest(1, least(20, p_limit));
$$;

grant execute on function public.find_similar_signals(text, vector, integer, integer) to service_role;
alter default privileges in schema public grant execute on functions to service_role;
```

**Verify** (returns 1 row with the function's signature):

```sql
select proname, pg_get_function_identity_arguments(oid) as args
  from pg_proc where proname = 'find_similar_signals';
```

The function is already in the canonical [`schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) (CREATE OR REPLACE), so re-applying the full file works too.

---

## 2026-06-01 — schema v0.4.0: Ehrenthal four-signal scheme

Migrates `signals.dimension` from the legacy 9-key v0.3.0 set to the 18-key
v0.4.0 set aligned with **Ehrenthal, Gonzalez-Padron & Gruen (2026)**'s
official four-signal scheme. Adds two columns:

- `signal_type` — Ehrenthal's top-level category (legitimacy /
  customer_cocreation / community_ecosystem / future_trajectory)
- `dimension_legacy` — preserves the original v0.3.0 value so pre-migration
  analyses are still reproducible

Required after pulling commits in the "schema v0.4.0" merge or later;
without it, the API still works (labels.py normalises legacy keys) but
the new charts that group by `signal_type` will see NULL.

**Paste this into the Supabase SQL editor and Run:**

```sql
alter table public.signals add column if not exists signal_type      text;
alter table public.signals add column if not exists dimension_legacy text;

update public.signals
   set dimension_legacy = dimension
 where dimension_legacy is null;

update public.signals set dimension = case dimension
    when 'technical_capability'       then 'technological_advances'
    when 'research_output'            then 'publications'
    when 'ip_filing'                  then 'patents'
    when 'infrastructure_or_facility' then 'hpc_collaborations'
    when 'partnership_or_alliance'    then 'industry_partnerships'
    when 'funding_or_grant'           then 'funding_event'
    when 'hiring_or_talent'           then 'leadership_expertise'
    when 'regulatory_or_policy'       then 'regulatory_recognition'
    when 'market_positioning'         then 'roadmaps'
    else dimension
 end
 where dimension in (
    'technical_capability', 'research_output', 'ip_filing',
    'infrastructure_or_facility', 'partnership_or_alliance',
    'funding_or_grant', 'hiring_or_talent', 'regulatory_or_policy',
    'market_positioning'
 );

update public.signals set signal_type = case dimension
    when 'leadership_expertise'        then 'legitimacy'
    when 'patents'                     then 'legitimacy'
    when 'publications'                then 'legitimacy'
    when 'awards'                      then 'legitimacy'
    when 'testimonials'                then 'legitimacy'
    when 'educational_outreach'        then 'legitimacy'
    when 'funding_event'               then 'legitimacy'
    when 'regulatory_recognition'      then 'legitimacy'
    when 'collaborations_applications' then 'customer_cocreation'
    when 'pilots_pocs'                 then 'customer_cocreation'
    when 'customer_training'           then 'customer_cocreation'
    when 'cloud_platform_listings'     then 'community_ecosystem'
    when 'hpc_collaborations'          then 'community_ecosystem'
    when 'industry_partnerships'       then 'community_ecosystem'
    when 'academic_partnerships'       then 'community_ecosystem'
    when 'roadmaps'                    then 'future_trajectory'
    when 'milestones'                  then 'future_trajectory'
    when 'technological_advances'      then 'future_trajectory'
    when 'long_horizon_claims'         then 'future_trajectory'
    else signal_type
 end
 where signal_type is null;

create index if not exists signals_signal_type_idx       on public.signals (signal_type);
create index if not exists signals_dimension_legacy_idx on public.signals (dimension_legacy);
```

**Verify** (every signal now has both a v0.4.0 dimension and a signal_type):

```sql
select dimension, signal_type, count(*)
  from public.signals
 group by 1, 2
 order by signal_type, dimension;
```

Idempotent — re-running the block is a no-op once migrated.

---

## 2026-06-02 — `signal_flags` table (Workflow B from wrong-signals-strategy.md)

Adds the `signal_flags` table the `/api/signal-flags` endpoint writes to.
Users (Anna, supervisor, reviewers) flag wrong signals via the Report
button on the website; the cron's Persistence step refuses to re-insert
any flagged `(actor_slug, source_url, content_hash)` tuple. The aggregate
flag rate by source / system / actor-category is a thesis-citable
quality metric (Chapter 3.5 quality leg).

Required after pulling commits in the "signal_flags" merge or later;
without it, hitting `POST /api/signal-flags` will return a 500.

**Paste this into the Supabase SQL editor and Run:**

```sql
create table if not exists public.signal_flags (
    id          uuid primary key default gen_random_uuid(),
    signal_id   uuid not null references public.signals(id) on delete cascade,
    reason      text not null check (reason in (
        'wrong_actor', 'off_topic', 'wrong_dimension',
        'low_quality', 'duplicate', 'other'
    )),
    note        text,
    flagged_at  timestamptz not null default now(),
    flagged_by  text
);

create index if not exists signal_flags_signal_idx on public.signal_flags (signal_id);
create index if not exists signal_flags_reason_idx on public.signal_flags (reason);
create index if not exists signal_flags_flagged_at_idx on public.signal_flags (flagged_at);

grant all on public.signal_flags to service_role;
```

**Verify** (returns 0 rows on a fresh install):

```sql
select count(*) from public.signal_flags;
```

The table is in the canonical `schema.sql` (idempotent), so re-applying the
full file works too.

---

## 2026-06-02 — v0.4.2 schema: defense_signals + stakeholder + human-validation + learning-loop + correct_example flag

Adds the v0.4.2 columns + the learning-loop infrastructure. **Self-contained + idempotent** — safe to paste in any state (fresh project, post-v0.4.0, post-v0.4.1) and safe to re-run.

If the prior `signal_flags` migration (the 2026-06-02 v0.4.0 Workflow B block above) wasn't applied, the v0.4.2 block creates the table itself rather than failing with `relation "public.signal_flags" does not exist`.

**Paste this into the Supabase SQL editor and Run:**

```sql
-- ---------- Prerequisite: signal_flags table (idempotent self-heal) ----------
-- The false_positives_recent view below depends on this table. If the
-- prior Workflow B migration was applied, this is a no-op. If not, we
-- create the table with the v0.4.2 reason set so the migration is
-- self-sufficient.
create table if not exists public.signal_flags (
    id          uuid primary key default gen_random_uuid(),
    signal_id   uuid not null references public.signals(id) on delete cascade,
    reason      text not null check (reason in (
        'wrong_actor', 'off_topic', 'wrong_dimension',
        'low_quality', 'duplicate', 'other',
        'correct_example'  -- v0.4.2 positive label (Anna's labelling)
    )),
    note        text,
    flagged_at  timestamptz not null default now(),
    flagged_by  text
);
create index if not exists signal_flags_signal_idx     on public.signal_flags (signal_id);
create index if not exists signal_flags_reason_idx     on public.signal_flags (reason);
create index if not exists signal_flags_flagged_at_idx on public.signal_flags (flagged_at);
grant all on public.signal_flags to service_role;

-- ---------- v0.4.2 — new columns on signals ----------
alter table public.signals add column if not exists stakeholder      text;
alter table public.signals add column if not exists human_validated  boolean not null default false;
alter table public.signals add column if not exists validator_notes  text;
alter table public.signals add column if not exists validated_by     text;
alter table public.signals add column if not exists validated_at     timestamptz;
alter table public.signals add column if not exists prompt_version   text;
create index if not exists signals_stakeholder_idx on public.signals (stakeholder);
create index if not exists signals_validated_idx   on public.signals (human_validated) where human_validated = true;

-- ---------- v0.4.2 — learning-loop tables ----------
create table if not exists public.missed_signals (
    id              uuid primary key default gen_random_uuid(),
    actor_slug      text not null references public.actors(slug),
    source_url      text not null,
    title           text,
    summary         text,
    expected_dimension    text,
    expected_signal_type  text,
    why_missed            text,
    manual_correction     text,
    found_by              text,
    found_at              timestamptz not null default now()
);
create index if not exists missed_signals_actor_idx on public.missed_signals (actor_slug);

create or replace view public.false_positives_recent as
    select f.id as flag_id, f.signal_id, f.reason, f.note, f.flagged_at,
           s.actor_slug, s.dimension, s.signal_type, s.source_kind,
           s.source_url, s.title, s.evidence_quote, s.confidence,
           s.system
      from public.signal_flags f
      join public.signals s on s.id = f.signal_id
     where f.flagged_at > now() - interval '90 days';
grant select on public.false_positives_recent to service_role;
grant all on public.missed_signals to service_role;

-- ---------- v0.4.2 — extend signal_flags reason CHECK if it pre-existed ----------
-- This is a no-op on fresh installs (the CREATE TABLE above already includes
-- 'correct_example'). It rewrites the constraint only when the table existed
-- previously with the v0.4.0 reason set (no 'correct_example').
do $$ begin
    if exists (
        select 1 from pg_constraint
        where conname = 'signal_flags_reason_check'
          and conrelid = 'public.signal_flags'::regclass
          and not pg_get_constraintdef(oid) ilike '%correct_example%'
    ) then
        alter table public.signal_flags drop constraint signal_flags_reason_check;
        alter table public.signal_flags add constraint signal_flags_reason_check
            check (reason in (
                'wrong_actor', 'off_topic', 'wrong_dimension',
                'low_quality', 'duplicate', 'other', 'correct_example'
            ));
    end if;
end $$;
```

**Verify:**

```sql
-- All new columns present:
select column_name from information_schema.columns
 where table_name='signals' and column_name in
       ('stakeholder','human_validated','validator_notes','validated_by','validated_at','prompt_version');
-- Learning-loop view returns rows joinable with signals:
select count(*) from public.false_positives_recent;
-- correct_example reason now allowed:
insert into public.signal_flags(signal_id, reason)
  select id, 'correct_example' from public.signals limit 1;
delete from public.signal_flags where reason = 'correct_example';  -- cleanup
```

---

## How to apply

1. Open <https://supabase.com/dashboard> → your project → **SQL editor**
2. Paste the latest unapplied snippet from this file
3. Click **Run**
4. If a snippet is idempotent (all current ones are), re-running it is a no-op

---

## Future migrations

Append a new section to this file with:
- date
- short rationale
- the SQL block (must be idempotent)
- a verification query

Then update `systems/masfactory/masfactory_system/persistence/schema.sql` to make the change canonical for fresh deployments.
