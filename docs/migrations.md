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
