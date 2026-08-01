"""The signals uniqueness key must be identical in the schema and every writer.

v0.5.0 added `system` to the unique constraint on public.signals so each
producer records its own findings independently. Two of the three writers were
updated with the migration; `sync_manual_signals.py` was not, and PostgREST
rejects an ON CONFLICT specification that does not match a real constraint:

    HTTP 400 {"code":"42P10","message":"there is no unique or exclusion
              constraint matching the ON CONFLICT specification"}

Nothing caught it, because each writer is exercised separately and the failure
only appears against a live database. In production the nightly manual-signal
sync failed on every run for three and a half weeks before anyone looked at
/var/log/manual_sync.log.

These tests compare the three specifications against the constraint declared in
schema.sql, so any future change to the key has to be made in all four places
or the suite goes red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import masfactory_system


# Resolve against the installed package rather than the test file, so the suite
# works both from a repo checkout and from `pip install .` in CI.
MASFACTORY = Path(masfactory_system.__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = MASFACTORY / "persistence" / "schema.sql"
SUPABASE_CLIENT = MASFACTORY / "persistence" / "supabase_client.py"
SYNC_MANUAL = MASFACTORY / "scripts" / "sync_manual_signals.py"
HERMES_PERSISTER = REPO_ROOT / "systems" / "hermes" / "scripts" / "persist_signals.py"

EXPECTED_KEY = ("actor_slug", "content_hash", "source_url", "system")


def _normalise(spec: str) -> tuple[str, ...]:
    """Column order is irrelevant to Postgres; compare as a sorted tuple."""
    return tuple(sorted(c.strip() for c in spec.split(",") if c.strip()))


def _signal_keys_in(path: Path) -> list[tuple[str, ...]]:
    """Every on_conflict specification in a file that targets public.signals.

    Read as text rather than imported. For the System B persister that is a hard
    requirement (the comparison-validity invariant forbids System A importing it)
    and a consistency check does not need the module loaded either way.
    """
    src = path.read_text(encoding="utf-8")
    specs = [
        # Inline literal: on_conflict="a,b,c" or ?on_conflict=a,b,c in a URL.
        *re.findall(r'on_conflict=["\']?([a-z_][a-z_,]*)', src),
        # Named constant: SIGNALS_ON_CONFLICT = "a,b,c". sync_manual_signals
        # routes its key through one, so matching only the inline form would
        # silently find nothing and pass a file that never upserts at all.
        *re.findall(r'^[A-Z_]*ON_CONFLICT[A-Z_]*\s*=\s*["\']([a-z_,]+)["\']', src, re.M),
    ]
    return [_normalise(s) for s in specs if "content_hash" in s]


def test_schema_declares_the_four_column_unique_constraint():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    match = re.search(
        r"add constraint signals_actor_url_hash_system_key\s*\n?\s*unique \(([^)]*)\)",
        sql,
        re.IGNORECASE,
    )
    assert match, "schema.sql must declare signals_actor_url_hash_system_key"
    assert _normalise(match.group(1)) == EXPECTED_KEY


def test_inline_table_definition_matches_the_migration():
    """`create table public.signals (... unique (...))` and the idempotent
    migration block further down must not drift apart, or a fresh bootstrap and
    a migrated database end up with different constraints."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    match = re.search(r"unique \(actor_slug, source_url, content_hash, system\)", sql)
    assert match, "the create-table block must carry the four-column unique key"


def test_sync_manual_signals_matches_the_constraint():
    """The writer that regressed. This is the assertion that would have failed
    on the v0.5.0 commit."""
    keys = _signal_keys_in(SYNC_MANUAL)
    assert keys, "sync_manual_signals.py must upsert signals with an explicit key"
    for key in keys:
        assert key == EXPECTED_KEY


def test_system_a_persister_matches_the_constraint():
    keys = _signal_keys_in(SUPABASE_CLIENT)
    assert keys, "supabase_client.py must upsert signals with an explicit key"
    for key in keys:
        assert key == EXPECTED_KEY


@pytest.mark.skipif(
    not HERMES_PERSISTER.is_file(),
    reason="System B wrapper is not present (running from an installed package "
           "rather than a repo checkout)",
)
def test_system_b_persister_matches_the_constraint():
    keys = _signal_keys_in(HERMES_PERSISTER)
    assert keys, "persist_signals.py must upsert signals with an explicit key"
    for key in keys:
        assert key == EXPECTED_KEY


def test_the_named_constant_is_exported_and_correct():
    """sync_manual_signals builds its URL from a module constant so the key has
    one obvious place to change. Imported here rather than in the module header
    so a regression shows up as an assertion, not a collection error."""
    from masfactory_system.scripts.sync_manual_signals import SIGNALS_ON_CONFLICT

    assert _normalise(SIGNALS_ON_CONFLICT) == EXPECTED_KEY


def test_all_writers_agree_with_each_other():
    """Belt and braces: whatever the key becomes, every writer must state the
    same thing. This is the check that generalises past the current bug."""
    found: dict[str, set] = {
        "sync_manual_signals": set(_signal_keys_in(SYNC_MANUAL)),
        "supabase_client": set(_signal_keys_in(SUPABASE_CLIENT)),
    }
    if HERMES_PERSISTER.is_file():
        found["persist_signals"] = set(_signal_keys_in(HERMES_PERSISTER))

    all_keys = set().union(*found.values())
    assert len(all_keys) == 1, f"writers disagree on the signals key: {found}"
