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
