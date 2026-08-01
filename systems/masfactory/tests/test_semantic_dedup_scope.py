"""Semantic dedup must not let one producer suppress the other.

v0.5.0 put `system` into the uniqueness key on public.signals precisely so
System A and System B each record their OWN copy of a finding both made. The
optional semantic-dedup layer was not updated to match: find_similar_signals
searched the whole corpus, so a near-identical row already written by System B
made System A drop its own record of the same event.

Two layers of the same system disagreed, and the vector layer won because it
runs before the insert. The suppression was also one-directional, since System
B runs no semantic dedup at all.

Cross-system overlap is a MEASUREMENT (eval_app.metrics.inter_system_agreement),
not a duplicate to delete. These tests pin that.
"""

from __future__ import annotations

import re
from pathlib import Path

import masfactory_system
from masfactory_system.persistence import supabase_client as sc
from masfactory_system.persistence.supabase_client import SupabaseStore

# Resolved lazily rather than imported by name: on the pre-fix module the
# constant does not exist, and a module-level ImportError would abort collection
# and hide every other assertion in this file.
SYSTEM = getattr(sc, "SYSTEM", "masfactory")


MASFACTORY = Path(masfactory_system.__file__).resolve().parent
SCHEMA_SQL = MASFACTORY / "persistence" / "schema.sql"
MIGRATION = (MASFACTORY / "persistence" / "migrations"
             / "v0.5.3-per-system-semantic-dedup.sql")


class _RecordingRPC:
    """Captures the parameters handed to client.rpc(), returns a fixed row."""

    def __init__(self, row):
        self.row = row
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name, params):
        self.calls.append((name, dict(params)))
        outer = self

        class _Exec:
            def execute(self_inner):
                class _Resp:
                    data = [outer.row] if outer.row is not None else []
                return _Resp()

        return _Exec()


def _store(row) -> tuple[SupabaseStore, _RecordingRPC]:
    fake = _RecordingRPC(row)
    store = SupabaseStore.__new__(SupabaseStore)  # bypass credential checks
    store._client = fake
    return store, fake


# ---------- the call the persister makes ----------

def test_lookup_is_scoped_to_this_system_by_default():
    """The regression. Without p_system the RPC searched every producer."""
    store, fake = _store(None)

    store.find_similar_signal(actor_slug="a1", embedding=[0.0] * 768, days_back=90)

    name, params = fake.calls[0]
    assert name == "find_similar_signals"
    assert "p_system" in params, "the neighbour search must be scoped to one producer"
    assert params["p_system"] == "masfactory"
    assert getattr(sc, "SYSTEM", None) == "masfactory", \
        "the producer name should be a named constant, not repeated literals"


def test_scope_can_be_widened_deliberately():
    """None still searches the whole corpus, for ad-hoc cross-system queries."""
    store, fake = _store(None)

    store.find_similar_signal(
        actor_slug="a1", embedding=[0.0] * 768, days_back=90, system=None
    )

    assert fake.calls[0][1]["p_system"] is None


def test_other_parameters_are_unchanged():
    store, fake = _store(None)

    store.find_similar_signal(actor_slug="a1", embedding=[0.1] * 768, days_back=42)

    params = fake.calls[0][1]
    assert params["p_actor_slug"] == "a1"
    assert params["p_days_back"] == 42
    assert params["p_limit"] == 1
    assert len(params["p_query_embedding"]) == 768


def test_rpc_failure_fails_open():
    """A database still on the 4-argument function rejects the 5-argument call.
    That must mean 'no near-duplicate found', never 'drop the signal', so the
    deploy order of this change cannot cost signals."""
    class _Boom:
        def rpc(self, *_a, **_k):
            raise RuntimeError("PGRST202: function not found")

    store = SupabaseStore.__new__(SupabaseStore)
    store._client = _Boom()

    assert store.find_similar_signal(actor_slug="a1", embedding=[0.0] * 768) is None


def test_a_same_system_neighbour_is_still_returned():
    """Scoping must not disable within-system dedup, which is the feature."""
    store, _ = _store({"id": "s1", "system": "masfactory", "similarity": 0.97,
                       "title": "t", "evidence_quote": "e", "source_url": "u",
                       "inserted_at": "2026-08-01T00:00:00+00:00"})

    hit = store.find_similar_signal(actor_slug="a1", embedding=[0.0] * 768)

    assert hit["similarity"] == 0.97
    assert hit["system"] == "masfactory"


# ---------- the SQL side ----------

def _fn_body(sql: str) -> str:
    start = sql.index("create or replace function public.find_similar_signals")
    return sql[start:sql.index("$$;", start)]


def test_schema_function_takes_and_applies_p_system():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    body = _fn_body(sql)
    assert "p_system text default null" in body, "the function must accept p_system"
    assert "(p_system is null or s.system = p_system)" in body, \
        "the neighbour search must filter on it"


def test_schema_drops_the_old_signature_before_recreating():
    """Adding a parameter changes the signature, so CREATE OR REPLACE alone
    would leave the 4-argument version behind as an overload and callers would
    silently keep hitting it."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    drop_at = sql.index("drop function if exists public.find_similar_signals(text, vector, integer, integer)")
    create_at = sql.index("create or replace function public.find_similar_signals")
    assert drop_at < create_at, "the DROP must precede the CREATE"


def test_grant_matches_the_new_signature():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    assert re.search(
        r"grant execute on function public\.find_similar_signals\("
        r"text, vector, integer, integer, text\) to service_role",
        sql,
    ), "service_role must be granted on the 5-argument signature"


def test_standalone_migration_matches_schema_sql():
    """The hand-run migration and the bootstrap schema must not drift."""
    assert MIGRATION.is_file(), "the v0.5.3 migration file must exist"
    migration = MIGRATION.read_text(encoding="utf-8")
    for fragment in (
        "drop function if exists public.find_similar_signals(text, vector, integer, integer)",
        "p_system text default null",
        "(p_system is null or s.system = p_system)",
        "find_similar_signals(text, vector, integer, integer, text) to service_role",
    ):
        assert fragment in migration, f"migration is missing: {fragment}"
