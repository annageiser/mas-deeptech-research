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
    source_kind     text not null check (source_kind in ('arxiv', 'website', 'swissreg', 'manual')),
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

create index if not exists signals_actor_idx on public.signals (actor_slug);
create index if not exists signals_dimension_idx on public.signals (dimension);
create index if not exists signals_run_idx on public.signals (run_id);
-- vector index left optional — populate first, then create via the Supabase UI
-- create index on public.signals using ivfflat (embedding vector_cosine_ops) with (lists = 100);

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

-- ---------- grants ----------
-- Supabase newer projects do not auto-grant service_role on user-created
-- tables in `public`. Both systems use the service_role key (not the anon
-- key) so they need explicit grants. Idempotent — safe to re-run.
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
alter default privileges in schema public grant all on tables    to service_role;
alter default privileges in schema public grant all on sequences to service_role;
