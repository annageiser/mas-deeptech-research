"""SQLite-backed Memory Manager — procedural + preference memory.

Schema (auto-created on first use):

  preference_facts(key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)
  procedural_skills(
      id INTEGER PRIMARY KEY,
      actor_slug TEXT,
      summary TEXT,
      successful_sources TEXT,        -- JSON list
      common_signal_dimensions TEXT,  -- JSON list
      created_at TIMESTAMP
  )
  run_log(
      id INTEGER PRIMARY KEY,
      run_id TEXT,
      actor_slug TEXT,
      signals_found INTEGER,
      brief TEXT,
      started_at TIMESTAMP,
      finished_at TIMESTAMP
  )

The Memory Manager is intentionally simple — the thesis can replace this with
a vector store or a graph DB later without touching the AIAgent core loop.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional


_SCHEMA = """
create table if not exists preference_facts (
    key         text primary key,
    value       text not null,
    updated_at  timestamp not null default current_timestamp
);

create table if not exists procedural_skills (
    id                          integer primary key autoincrement,
    actor_slug                  text not null,
    summary                     text not null,
    successful_sources          text not null default '[]',
    common_signal_dimensions    text not null default '[]',
    created_at                  timestamp not null default current_timestamp
);

create index if not exists procedural_skills_actor_idx
    on procedural_skills(actor_slug);

create table if not exists run_log (
    id              integer primary key autoincrement,
    run_id          text not null,
    actor_slug      text not null,
    signals_found   integer not null default 0,
    brief           text,
    started_at      timestamp not null default current_timestamp,
    finished_at     timestamp
);

create index if not exists run_log_actor_idx on run_log(actor_slug);
create index if not exists run_log_run_idx   on run_log(run_id);
"""


class MemoryManager:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._initialise()

    def _initialise(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- preference facts ----------

    def set_preference(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "insert into preference_facts(key, value, updated_at) values (?,?,?) "
                "on conflict(key) do update set value=excluded.value, updated_at=excluded.updated_at",
                (key, value, datetime.now(timezone.utc).isoformat()),
            )

    def list_preferences(self) -> list[tuple[str, str]]:
        with self._conn() as conn:
            cur = conn.execute("select key, value from preference_facts order by key")
            return [(r["key"], r["value"]) for r in cur.fetchall()]

    # ---------- procedural skills ----------

    def record_procedure(
        self,
        actor_slug: str,
        summary: str,
        successful_sources: Iterable[str],
        common_signal_dimensions: Iterable[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "insert into procedural_skills(actor_slug, summary, successful_sources, common_signal_dimensions)"
                " values (?,?,?,?)",
                (
                    actor_slug,
                    summary,
                    json.dumps(list(successful_sources)),
                    json.dumps(list(common_signal_dimensions)),
                ),
            )

    def recall_procedure(self, actor_slug: str, *, limit: int = 3) -> list[dict[str, object]]:
        with self._conn() as conn:
            cur = conn.execute(
                "select summary, successful_sources, common_signal_dimensions, created_at"
                " from procedural_skills where actor_slug=? order by created_at desc limit ?",
                (actor_slug, limit),
            )
            results: list[dict[str, object]] = []
            for r in cur.fetchall():
                results.append(
                    {
                        "summary": r["summary"],
                        "successful_sources": json.loads(r["successful_sources"]),
                        "common_signal_dimensions": json.loads(r["common_signal_dimensions"]),
                        "created_at": r["created_at"],
                    }
                )
            return results

    # ---------- run log ----------

    def log_run_start(self, run_id: str, actor_slug: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "insert into run_log(run_id, actor_slug) values (?,?)",
                (run_id, actor_slug),
            )
            return int(cur.lastrowid or 0)

    def log_run_finish(self, row_id: int, signals_found: int, brief: Optional[str] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "update run_log set signals_found=?, brief=?, finished_at=current_timestamp where id=?",
                (signals_found, brief, row_id),
            )
