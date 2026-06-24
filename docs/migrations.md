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

## 2026-06-04 — v0.4.3: industry_news table for worldwide quantum news

Adds the unattributed industry-news table backing the new /quantum-news page.

**Paste this into the Supabase SQL editor and Run:**

```sql
create table if not exists public.industry_news (
    id              uuid primary key default gen_random_uuid(),
    source_url      text not null,
    source_name     text not null,
    title           text not null,
    summary         text,
    published_at    timestamptz,
    fetched_at      timestamptz not null default now(),
    content_hash    text not null,
    unique (source_url, content_hash)
);
create index if not exists industry_news_published_idx on public.industry_news (published_at desc);
create index if not exists industry_news_source_idx    on public.industry_news (source_name);
grant all on public.industry_news to service_role;
```

**Verify:** `select count(*) from public.industry_news;` → `0` on fresh install.

After applying, run the populator once to seed:
```bash
ssh annageiser@187.127.87.208 'cd /opt/mas-deeptech-research && docker compose run --rm --entrypoint python reports -m reports_system.industry_news_runner'
```

---

## 2026-06-11 — v0.4.19: defense as boolean flags + Bug 1 backfill

Anna's design decision: `defense_engagement` and `defense_ambivalence` are **flags layered on top of** an Ehrenthal signal_type, not a fifth signal_type. A defense-related signal is *also* a legitimacy / customer_cocreation / community_ecosystem / future_trajectory signal — the flag just says it has a defense dimension too.

Also bundles **Bug 1 backfill**: rows with NULL `signal_type` (from pre-v0.4.0 data that the v0.4.0 dimension-rewrite map didn't cover) get reclassified to `community_ecosystem` with their original value preserved in `dimension_legacy`.

**Paste this into the Supabase SQL editor and Run:**

```sql
-- Step 1 — add the two boolean flag columns. Default false; existing rows
-- start as "not defense-related" and get flagged by step 2.
alter table public.signals
    add column if not exists defense_engagement boolean not null default false;
alter table public.signals
    add column if not exists defense_ambivalence boolean not null default false;

-- Step 2 — backfill flags from v0.4.2 defense-related dimension values.
-- v0.4.2 stored defense as signal_type='defense_signals' with
-- dimension IN ('defense_engagement','defense_ambivalence'). We migrate
-- those into the new flag columns.
update public.signals
   set defense_engagement = true
 where signal_type = 'defense_signals' and dimension = 'defense_engagement';

update public.signals
   set defense_ambivalence = true
 where signal_type = 'defense_signals' and dimension = 'defense_ambivalence';

-- Step 3 — reclassify the now-flagged rows to one of the four Ehrenthal types.
-- Conservative default: community_ecosystem (defense engagement is most often
-- a consortium / joint-project signal; ambivalence is a strategic-positioning
-- statement). The original dimension survives in dimension_legacy.
update public.signals
   set dimension_legacy = coalesce(dimension_legacy, dimension),
       dimension = case
           when dimension = 'defense_engagement'   then 'consortium_membership'
           when dimension = 'defense_ambivalence'  then 'strategic_positioning'
           else dimension
       end,
       signal_type = 'community_ecosystem'
 where signal_type = 'defense_signals';

-- Step 4 — Bug 1 backfill: rows with NULL signal_type get a default
-- classification + dimension_legacy preserves whatever they had.
update public.signals
   set signal_type = 'community_ecosystem',
       dimension_legacy = coalesce(dimension_legacy, dimension)
 where signal_type is null;

-- Step 5 — drop old CHECK constraints, add the v0.4.19 four-value-only one.
alter table public.signals
    drop constraint if exists signals_signal_type_check;
alter table public.signals
    drop constraint if exists signals_signal_type_check_v042;
alter table public.signals
    add constraint signals_signal_type_check_v0419
    check (signal_type in (
        'legitimacy', 'customer_cocreation',
        'community_ecosystem', 'future_trajectory'
    ));

-- Step 6 — partial indexes for fast flag-filtering.
create index if not exists signals_defense_engagement_idx
    on public.signals (defense_engagement) where defense_engagement = true;
create index if not exists signals_defense_ambivalence_idx
    on public.signals (defense_ambivalence) where defense_ambivalence = true;
```

**Verify:**
```sql
-- expect 0
select count(*) from public.signals where signal_type = 'defense_signals';

-- expect 0
select count(*) from public.signals where signal_type is null;

-- the new flags work
select signal_type, defense_engagement, defense_ambivalence, count(*)
from public.signals
group by 1, 2, 3
order by 4 desc;
```

After applying on Supabase, rebuild both agents so they pick up the new prompts + persister:
```bash
docker compose build masfactory hermes
```

---

## 2026-06-11 — v0.4.19d: actor-level defense_ambivalence marker (task D.2 / #106)

Per-signal flags say "this signal is defense-flavoured." The actor-level marker says "this actor exhibits the defense-ambivalence pattern as a persistent behaviour" — a different claim. Worth having both.

**Paste this into the Supabase SQL editor and Run:**

```sql
alter table public.actors
    add column if not exists defense_ambivalence_marker boolean not null default false;

alter table public.actors
    add column if not exists defense_ambivalence_marker_notes text;
```

**Seed for known cases** (edit the slugs to match what's in your `actors` table):

```sql
-- Example seed — uncomment and run for actors you've confirmed exhibit the pattern.
-- update public.actors
--    set defense_ambivalence_marker = true,
--        defense_ambivalence_marker_notes =
--          'Anna 2026-06-11: known US defense ties; deliberately opaque about quantum-specific work.'
--  where slug = 'd-wave';
```

The marker is hand-edited in the Supabase Table editor going forward. The systems do not auto-set it.

---

## 2026-06-12 — v0.4.24: sentiment columns on `signals` (task C.4 / #117)

Adds two columns so both systems can persist a per-signal sentiment score.
VADER lexicon (Hutto & Gilbert 2014) computed at persistence time on
`evidence_quote + summary`. Cross-system parity invariant: both A and B
use the same thresholds (±0.05) and composition.

```sql
alter table public.signals add column if not exists sentiment_score real;
alter table public.signals add column if not exists sentiment_label text;
create index if not exists signals_sentiment_label_idx
    on public.signals (sentiment_label);
```

Verification — both systems should show non-null `scored` after one
cron tick post-v0.4.24:

```sql
select system, count(*) total,
       count(*) filter (where sentiment_label is not null) scored
from public.signals
where inserted_at > now() - interval '6 hours'
group by system;
```

Pre-v0.4.24 rows remain NULL in both columns. The decision on whether
to backfill (longitudinal consistency) vs. score-forward only (clean
methodological cut) is left to the thesis evaluation chapter.

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

---

## 2026-06-24 — v0.4.37 manual signals + signal sources

Source: [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) at the v0.4.37 block.

Three new tables + one CHECK extension. Idempotent — safe to re-run.

**Paste this into the Supabase SQL editor and Run:**

```sql
-- 1. Allow 'manual' as a producer alongside masfactory + hermes.
do $$
begin
    if exists (
        select 1 from pg_constraint
        where conname = 'signals_system_check'
          and conrelid = 'public.signals'::regclass
          and not pg_get_constraintdef(oid) ilike '%manual%'
    ) then
        alter table public.signals drop constraint signals_system_check;
        alter table public.signals add constraint signals_system_check
            check (system in ('masfactory', 'hermes', 'manual'));
    end if;
end $$;

-- 2. Editorial signal layer (curated through /labels).
create table if not exists public.manual_signals (
    id              uuid primary key default gen_random_uuid(),
    source_url      text not null,
    title           text,
    notes           text,
    labels          text[] not null default '{}',
    signal_type     text,
    dimension       text,
    actor_slugs     text[] not null default '{}',
    created_by      text not null default 'anna',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    ingested_run_ids uuid[] not null default '{}',
    propagated_signal_id uuid references public.signals(id) on delete set null,
    propagated_at   timestamptz,
    unique (source_url)
);
create index if not exists manual_signals_labels_idx
    on public.manual_signals using gin (labels);
create index if not exists manual_signals_actors_idx
    on public.manual_signals using gin (actor_slugs);
create index if not exists manual_signals_updated_idx
    on public.manual_signals (updated_at desc);

-- 3. Source management (CRUD through /sources).
create table if not exists public.signal_sources (
    id                    uuid primary key default gen_random_uuid(),
    url                   text not null,
    kind                  text not null
        check (kind in ('rss', 'atom', 'url')),
    label                 text,
    notes                 text,
    labels                text[] not null default '{}',
    actor_slugs           text[] not null default '{}',
    enabled               boolean not null default true,
    crawl_frequency_hours integer not null default 24
        check (crawl_frequency_hours between 0 and 720),
    last_fetched_at       timestamptz,
    last_status           text,
    last_error            text,
    last_item_count       integer not null default 0,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    unique (url)
);
create index if not exists signal_sources_enabled_idx
    on public.signal_sources (enabled);
create index if not exists signal_sources_labels_idx
    on public.signal_sources using gin (labels);
create index if not exists signal_sources_actors_idx
    on public.signal_sources using gin (actor_slugs);

-- 4. Ingestion-history audit.
create table if not exists public.signal_source_runs (
    id              uuid primary key default gen_random_uuid(),
    source_id       uuid not null references public.signal_sources(id) on delete cascade,
    system          text check (system in ('masfactory', 'hermes', 'manual')),
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,
    status          text check (status in ('ok', 'error')),
    items_fetched   integer not null default 0,
    items_new       integer not null default 0,
    error_message   text
);
create index if not exists signal_source_runs_source_idx
    on public.signal_source_runs (source_id, started_at desc);

-- 5. updated_at trigger for both editorial tables.
create or replace function public._touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;
drop trigger if exists trg_manual_signals_touch on public.manual_signals;
create trigger trg_manual_signals_touch
    before update on public.manual_signals
    for each row execute function public._touch_updated_at();
drop trigger if exists trg_signal_sources_touch on public.signal_sources;
create trigger trg_signal_sources_touch
    before update on public.signal_sources
    for each row execute function public._touch_updated_at();
```

The grants block at the bottom of `schema.sql` covers these new
tables via `alter default privileges`, so service_role can read +
write them without an extra grant.
