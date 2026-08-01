-- v0.5.3 — scope semantic dedup to one producer.
--
-- Run this ONCE in the Supabase SQL Editor (Dashboard -> SQL Editor -> New
-- query -> paste -> Run). Also lives in schema.sql so a fresh bootstrap gets
-- the same result.
--
-- WHAT WAS WRONG
-- --------------
-- v0.5.0 put `system` into the uniqueness key on public.signals so System A
-- and System B each record their OWN findings, even when both discover the
-- same event. The optional semantic-dedup layer was never updated to match:
-- find_similar_signals searched the entire corpus regardless of producer, so
-- when System A was about to record something a near-identical System B row
-- already covered, System A dropped its own signal.
--
-- Two layers of the same system therefore disagreed. The row-level key said
-- "both producers may record this"; the vector layer said "only the first
-- one may". The vector layer won, because it runs before the insert.
--
-- The suppression was also one-directional. System B implements no semantic
-- dedup at all (HRM_SEMANTIC_DEDUP is read by nothing), so only System A
-- could lose signals, and it lost them against the larger corpus. On the
-- production database at the time of writing that is 2214 hermes rows versus
-- 1008 masfactory rows over 90 days, so the asymmetry ran against System A.
--
-- MEASURED IMPACT SO FAR: none. MASF_SEMANTIC_DEDUP=1 and MASF_EMBEDDINGS=1
-- are both on in production and the check has run for 52 recorded runs, but
-- the 0.92 cosine threshold was never crossed (`signals_dropped: 0` in every
-- data/raw/runs/*/semantic_dedup.json). Two systems writing their own title,
-- summary and evidence quote for the same event land far enough apart in
-- embedding space. So this is a latent defect being closed before it fires,
-- not damage being repaired. Nothing needs backfilling.
--
-- WHAT THIS CHANGES
-- -----------------
-- Adds a `p_system` parameter. When supplied, the neighbour search is scoped
-- to that producer's own rows. NULL preserves the old whole-corpus behaviour
-- for ad-hoc queries that genuinely want to ask the cross-system question.
--
-- Cross-system overlap remains fully visible and is still MEASURED, by
-- eval_app/metrics/inter_system_agreement.py. It is a finding, not a
-- duplicate to delete.
--
-- ORDER OF OPERATIONS
-- -------------------
-- Safe in either order. The Python wrapper catches every RPC error and
-- returns None, which the caller reads as "no near-duplicate found" and
-- proceeds with the insert. So a deployed image calling the 5-argument form
-- against an un-migrated database fails open (no suppression) rather than
-- dropping signals. Running the SQL first is still the tidier sequence.

-- The DROP is required, not defensive. Adding a parameter changes the
-- signature, so a bare CREATE OR REPLACE would leave the old 4-argument
-- function in place as an overload and every existing caller would keep
-- resolving to it.
drop function if exists public.find_similar_signals(text, vector, integer, integer);

create or replace function public.find_similar_signals(
    p_actor_slug text,
    p_query_embedding vector(768),
    p_days_back integer default 30,
    p_limit integer default 1,
    p_system text default null
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
      and (p_system is null or s.system = p_system)
    order by s.embedding <=> p_query_embedding asc
    limit greatest(1, least(20, p_limit));
$$;

grant execute on function public.find_similar_signals(text, vector, integer, integer, text) to service_role;

-- Verify: exactly one function, taking five arguments.
select p.oid::regprocedure as signature
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname = 'find_similar_signals';
