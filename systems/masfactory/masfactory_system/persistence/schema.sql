-- Supabase schema shared by both MAS systems (A: MASFactory, B: Hermes).
--
-- Apply once in the Supabase SQL editor. The container does NOT migrate at
-- startup — a cron-triggered runner must never have DDL side effects.

create extension if not exists vector;
create extension if not exists pgcrypto;

-- ---------- actors ----------
create table if not exists public.actors (
    slug            text primary key,
    name            text not null,
    category        text not null,
    homepage        text,
    arxiv_query     text,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- ---------- runs (one per g.invoke()) ----------
create table if not exists public.runs (
    id              uuid primary key default gen_random_uuid(),
    system          text not null check (system in ('masfactory', 'hermes')),
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,
    status          text not null default 'running' check (status in ('running', 'ok', 'error')),
    error_message   text,
    config_snapshot jsonb,                            -- env-derived settings
    actor_slugs     text[] not null default '{}'     -- which actors this run processed
);

-- ---------- signals ----------
create table if not exists public.signals (
    id              uuid primary key default gen_random_uuid(),
    run_id          uuid not null references public.runs(id) on delete cascade,
    actor_slug      text not null references public.actors(slug),
    system          text not null default 'masfactory' check (system in ('masfactory', 'hermes')),
    source_kind     text not null check (source_kind in ('arxiv', 'website', 'swissreg', 'manual', 'news')),
    source_url      text not null,
    title           text not null,
    summary         text not null,
    evidence_quote  text not null,
    dimension       text not null,
    is_technical    boolean not null,
    confidence      double precision not null check (confidence >= 0 and confidence <= 1),
    observed_at     timestamptz,
    inserted_at     timestamptz not null default now(),
    embedding       vector(768),
    content_hash    text not null,
    unique (actor_slug, source_url, content_hash)
);

-- Backwards-compat: if the table existed before `system` was added.
alter table public.signals add column if not exists system text;
update public.signals s set system = r.system
    from public.runs r where r.id = s.run_id and (s.system is null or s.system = '');
alter table public.signals alter column system set default 'masfactory';
alter table public.signals alter column system set not null;
do $$ begin
    if not exists (
        select 1 from information_schema.constraint_column_usage
        where table_name='signals' and constraint_name='signals_system_check'
    ) then
        alter table public.signals add constraint signals_system_check check (system in ('masfactory', 'hermes'));
    end if;
end $$;

create index if not exists signals_actor_idx on public.signals (actor_slug);
create index if not exists signals_dimension_idx on public.signals (dimension);
create index if not exists signals_run_idx on public.signals (run_id);
create index if not exists signals_system_idx on public.signals (system);

-- ---------- pgvector index (created once embeddings start populating) ----------
-- Idempotent — only created when there are non-null embeddings to build over.
-- Skipped silently otherwise so the schema script stays runnable on a fresh
-- Supabase project where MASF_EMBEDDINGS / HRM_EMBEDDINGS are still off.
do $$
declare
    n_embedded integer;
begin
    select count(*) into n_embedded from public.signals where embedding is not null;
    if n_embedded > 0 and not exists (
        select 1 from pg_indexes
        where schemaname = 'public' and indexname = 'signals_embedding_ivfflat_idx'
    ) then
        execute 'create index signals_embedding_ivfflat_idx '
             || 'on public.signals using ivfflat (embedding vector_cosine_ops) '
             || 'with (lists = 100)';
    end if;
end $$;

-- ---------- per-node token usage ----------
create table if not exists public.token_usage (
    id              uuid primary key default gen_random_uuid(),
    run_id          uuid not null references public.runs(id) on delete cascade,
    node_name       text not null,
    model_name      text not null,
    input_tokens    integer not null default 0,
    output_tokens   integer not null default 0,
    calls           integer not null default 0,
    recorded_at     timestamptz not null default now()
);

-- Backwards-compat: if the table existed before `calls` was added.
alter table public.token_usage add column if not exists calls integer not null default 0;

create index if not exists token_usage_run_idx on public.token_usage (run_id);

-- ---------- raw audit log ----------
create table if not exists public.audit_log (
    id              uuid primary key default gen_random_uuid(),
    run_id          uuid not null references public.runs(id) on delete cascade,
    node_name       text not null,
    payload         jsonb not null,
    created_at      timestamptz not null default now()
);

create index if not exists audit_log_run_idx on public.audit_log (run_id);

-- ---------- migrations (idempotent) ----------
-- Add 'news' to the allowed source_kind values for existing deployments
-- where the CHECK constraint was created before this migration shipped.
-- Safe to run repeatedly.
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

-- ---------- schema v0.4.0 migration: Ehrenthal four-signal scheme ----------
-- Adds two columns:
--   signal_type      — Ehrenthal's top-level four-signal scheme key
--   dimension_legacy — preserves the v0.3.0 dimension value
--
-- Then rewrites `signals.dimension` in place from the legacy nine-key set to
-- the new eighteen-key set, and back-fills `signal_type` from the (rewritten)
-- dimension. Idempotent — safe to re-run; the rewrite is keyed on the legacy
-- value set so re-runs are no-ops once migrated.
alter table public.signals add column if not exists signal_type      text;
alter table public.signals add column if not exists dimension_legacy text;
-- v0.4.19: defense as boolean flags overlaid on the Ehrenthal four
alter table public.signals add column if not exists defense_engagement  boolean not null default false;
alter table public.signals add column if not exists defense_ambivalence boolean not null default false;
-- v0.4.19d (task D.2): actor-level marker — different claim from the
-- per-signal flag. Hand-edited in Supabase; systems do not auto-set it.
alter table public.actors  add column if not exists defense_ambivalence_marker       boolean not null default false;
alter table public.actors  add column if not exists defense_ambivalence_marker_notes text;

-- Preserve the original value before we rewrite `dimension`. Only fills
-- rows that haven't been preserved yet so re-runs don't clobber.
update public.signals
   set dimension_legacy = dimension
 where dimension_legacy is null;

-- Remap v0.3.0 → v0.4.0 dimension keys in place. The mapping is the
-- canonical truth in schema.yaml (legacy_dimensions: on each entry) and
-- must stay in sync — classification.legacy_dimension_map() reads from
-- the same source.
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

-- Backfill signal_type from the (now-migrated) dimension.
update public.signals set signal_type = case dimension
    -- Legitimacy
    when 'leadership_expertise'        then 'legitimacy'
    when 'patents'                     then 'legitimacy'
    when 'publications'                then 'legitimacy'
    when 'awards'                      then 'legitimacy'
    when 'testimonials'                then 'legitimacy'
    when 'educational_outreach'        then 'legitimacy'
    when 'funding_event'               then 'legitimacy'
    when 'regulatory_recognition'      then 'legitimacy'
    -- Customer co-creation
    when 'collaborations_applications' then 'customer_cocreation'
    when 'pilots_pocs'                 then 'customer_cocreation'
    when 'customer_training'           then 'customer_cocreation'
    -- Community-ecosystem
    when 'cloud_platform_listings'     then 'community_ecosystem'
    when 'hpc_collaborations'          then 'community_ecosystem'
    when 'industry_partnerships'       then 'community_ecosystem'
    when 'academic_partnerships'       then 'community_ecosystem'
    -- Future-trajectory
    when 'roadmaps'                    then 'future_trajectory'
    when 'milestones'                  then 'future_trajectory'
    when 'technological_advances'      then 'future_trajectory'
    when 'long_horizon_claims'         then 'future_trajectory'
    else signal_type
 end
 where signal_type is null;

create index if not exists signals_signal_type_idx on public.signals (signal_type);
create index if not exists signals_dimension_legacy_idx on public.signals (dimension_legacy);

-- ---------- v0.4.2 stakeholder + human-validation + prompt_version ----------
-- Stakeholder lens: which audience the signal is primarily aimed at. Optional;
-- the Classifier fills it when it can, NULL when it can't.
alter table public.signals add column if not exists stakeholder text;
-- Human-validation layer: Anna marks signals as verified during her parallel
-- coding. The dashboard surfaces validated rows with a badge; the eval
-- harness uses them as gold-set entries.
alter table public.signals add column if not exists human_validated boolean not null default false;
alter table public.signals add column if not exists validator_notes text;
alter table public.signals add column if not exists validated_by   text;
alter table public.signals add column if not exists validated_at   timestamptz;
-- Prompt version recorded for traceability across iterations.
alter table public.signals add column if not exists prompt_version text;

create index if not exists signals_stakeholder_idx  on public.signals (stakeholder);
create index if not exists signals_validated_idx    on public.signals (human_validated) where human_validated = true;

-- ---------- v0.4.2 learning-loop tables ----------
-- missed_signals: things Anna saw in her manual coding (or in the wild) that
-- neither MAS system produced. Each row carries a why_missed hypothesis
-- (LLM-generated when possible) + a manual_correction field.
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

-- false_positives view: convenience view over signal_flags joined with
-- signals so the learning-loop weekly report can query in one shot.
create or replace view public.false_positives_recent as
    select f.id as flag_id, f.signal_id, f.reason, f.note, f.flagged_at,
           s.actor_slug, s.dimension, s.signal_type, s.source_kind,
           s.source_url, s.title, s.evidence_quote, s.confidence,
           s.system
      from public.signal_flags f
      join public.signals s on s.id = f.signal_id
     where f.flagged_at > now() - interval '90 days';
grant select on public.false_positives_recent to service_role;

-- ---------- v0.4.3 industry_news — worldwide quantum news (no actor) ----------
-- RSS / news entries that don't match any of the 40 Swiss actors but are
-- still relevant quantum-computing news. Surfaced on the website's
-- /quantum-news page; never participates in per-actor scoring.
create table if not exists public.industry_news (
    id              uuid primary key default gen_random_uuid(),
    source_url      text not null,
    source_name     text not null,          -- e.g. "The Quantum Insider"
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

-- ---------- signal_flags — user-reported wrong signals (Workflow B) ----------
-- See docs/wrong-signals-strategy.md. Anna (or anyone with access to the
-- dashboard) can flag a wrong signal via the /api/signal-flags endpoint;
-- the cron's Persistence step refuses to re-insert any signal whose
-- (actor_slug, source_url, content_hash) matches a flagged row. The
-- aggregate "wrong-signal rate" by source / system / actor category is
-- a thesis-citable quality metric (Chapter 3.5 quality leg).
create table if not exists public.signal_flags (
    id          uuid primary key default gen_random_uuid(),
    signal_id   uuid not null references public.signals(id) on delete cascade,
    reason      text not null check (reason in (
        'wrong_actor', 'off_topic', 'wrong_dimension',
        'low_quality', 'duplicate', 'other',
        -- v0.4.2: positive label — Anna marks a signal as a correct
        -- example to teach the Classifier (few-shot exemplar).
        'correct_example'
    )),
    note        text,
    flagged_at  timestamptz not null default now(),
    -- Optional source-tracking. Empty in v0.4.0 (flagging is anonymous);
    -- reserved for a future labelled-rater workflow.
    flagged_by  text
);

create index if not exists signal_flags_signal_idx on public.signal_flags (signal_id);
create index if not exists signal_flags_reason_idx on public.signal_flags (reason);
create index if not exists signal_flags_flagged_at_idx on public.signal_flags (flagged_at);

-- ---------- semantic-dedup RPC (uses pgvector cosine distance) ----------
-- Returns the nearest existing signals for a given (actor_slug, query
-- embedding) pair within the last N days. The persistence step calls this
-- before insert and drops signals whose nearest neighbour is closer than
-- the configured threshold (default 0.92 cosine similarity).
--
-- Idempotent — CREATE OR REPLACE makes this safe to re-run on every
-- schema.sql apply.
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

-- ---------- grants ----------
-- Supabase newer projects do not auto-grant service_role on user-created
-- tables in `public`. Both systems use the service_role key (not the anon
-- key) so they need explicit grants. Idempotent — safe to re-run.
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant execute on function public.find_similar_signals(text, vector, integer, integer) to service_role;
alter default privileges in schema public grant all on tables    to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant execute on functions to service_role;
