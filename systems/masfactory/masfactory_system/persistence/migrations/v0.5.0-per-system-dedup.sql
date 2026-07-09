-- v0.5.0 — per-system signal dedup migration.
--
-- Run this ONCE in the Supabase SQL Editor (Dashboard → SQL Editor → New query
-- → paste → Run) BEFORE deploying the v0.5.0 persistence code. It swaps the
-- signals uniqueness key from 3 columns to 4 (adds `system`) so each
-- architecture — masfactory (System A) and hermes (System B) — records its OWN
-- findings independently instead of the first-runner silently owning a signal
-- both found. This is the mirror of the on_conflict change in
-- supabase_client.py (System A) and persist_signals.py (System B).
--
-- Safe on the live table: adding a column to a unique key only RELAXES it, so
-- no existing row can violate the new constraint. Idempotent — re-running is a
-- no-op. Also lives in schema.sql so a fresh bootstrap gets the same result.
--
-- ORDER OF OPERATIONS (important — the old code and new code each need THEIR
-- matching constraint, so don't leave a gap across a cron tick):
--   1. Run this migration.
--   2. Rebuild + redeploy the masfactory + hermes images (new on_conflict).
-- Do both before the next 02:00/05:00 cron.

do $$
declare old_name text;
begin
    -- Drop the old 3-column unique constraint, whatever its generated name is.
    select con.conname into old_name
    from pg_constraint con
    where con.conrelid = 'public.signals'::regclass
      and con.contype = 'u'
      and (
        select array_agg(att.attname::text order by att.attname::text)
        from unnest(con.conkey) as k
        join pg_attribute att on att.attrelid = con.conrelid and att.attnum = k
      ) = array['actor_slug', 'content_hash', 'source_url']::text[]
    limit 1;
    if old_name is not null then
        execute format('alter table public.signals drop constraint %I', old_name);
        raise notice 'dropped old 3-column unique constraint: %', old_name;
    end if;

    -- Add the 4-column unique constraint (includes `system`).
    if not exists (
        select 1 from pg_constraint con
        where con.conrelid = 'public.signals'::regclass
          and con.contype = 'u'
          and (
            select array_agg(att.attname::text order by att.attname::text)
            from unnest(con.conkey) as k
            join pg_attribute att on att.attrelid = con.conrelid and att.attnum = k
          ) = array['actor_slug', 'content_hash', 'source_url', 'system']::text[]
    ) then
        alter table public.signals
            add constraint signals_actor_url_hash_system_key
            unique (actor_slug, source_url, content_hash, system);
        raise notice 'added 4-column unique constraint signals_actor_url_hash_system_key';
    end if;
end $$;

-- Verify (should list exactly one unique constraint over the 4 columns):
select conname,
       (select array_agg(att.attname order by att.attnum)
        from unnest(con.conkey) as k
        join pg_attribute att on att.attrelid = con.conrelid and att.attnum = k) as columns
from pg_constraint con
where con.conrelid = 'public.signals'::regclass and con.contype = 'u';
