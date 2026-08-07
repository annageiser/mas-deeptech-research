"""Pull July 2026 signals, actors, runs, and token_usage from Supabase Postgres.

Writes four CSVs into data/ that all figures downstream read. Run once when the
window closes; the figure scripts are then reproducible without live DB access.

Credentials come from env only — do NOT commit them. Use one of:

    export SUPABASE_DB_URL='postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres'

or set SUPABASE_DB_{HOST,PORT,NAME,USER,PASSWORD} individually.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

WINDOW_START = "2026-07-01 00:00:00+00"
WINDOW_END = "2026-08-01 00:00:00+00"


def conn_kwargs() -> dict:
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if url:
        p = urlparse(url)
        return dict(
            host=p.hostname,
            port=p.port or 5432,
            dbname=(p.path or "/postgres").lstrip("/"),
            user=p.username,
            password=p.password,
            sslmode="require",
        )
    required = ["SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    if missing:
        sys.exit(f"missing env: {missing} (or set SUPABASE_DB_URL)")
    return dict(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ.get("SUPABASE_DB_PORT", "5432")),
        dbname=os.environ.get("SUPABASE_DB_NAME", "postgres"),
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
    )


def dump(cur, sql: str, params: tuple, out: Path) -> int:
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)


def main() -> None:
    with psycopg.connect(**conn_kwargs()) as conn, conn.cursor() as cur:
        n_actors = dump(cur, "select slug, name, category, homepage from public.actors order by slug", (), DATA / "july_2026_actors.csv")
        print(f"actors: {n_actors}")

        n_signals = dump(
            cur,
            """select id, actor_slug, system, source_kind, source_url,
                      dimension, signal_type, inserted_at, observed_at,
                      confidence, defense_engagement, defense_ambivalence
               from public.signals
               where inserted_at >= %s and inserted_at < %s
               order by inserted_at""",
            (WINDOW_START, WINDOW_END),
            DATA / "july_2026_signals.csv",
        )
        print(f"signals: {n_signals}")

        n_tokens = dump(
            cur,
            """select tu.run_id, tu.node_name, tu.model_name,
                      tu.input_tokens, tu.output_tokens, tu.calls, tu.recorded_at,
                      r.system
               from public.token_usage tu
               join public.runs r on r.id = tu.run_id
               where tu.recorded_at >= %s and tu.recorded_at < %s""",
            (WINDOW_START, WINDOW_END),
            DATA / "july_2026_token_usage.csv",
        )
        print(f"token_usage: {n_tokens}")

        n_runs = dump(
            cur,
            """select id, system, started_at, finished_at, status, actor_slugs
               from public.runs
               where started_at >= %s and started_at < %s""",
            (WINDOW_START, WINDOW_END),
            DATA / "july_2026_runs.csv",
        )
        print(f"runs: {n_runs}")

    print("done — CSVs saved under data/")


if __name__ == "__main__":
    main()
