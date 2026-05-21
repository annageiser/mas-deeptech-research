"""Weekly per-system report generator."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .config import Settings
from .openrouter import OpenRouterClient
from .output_writer import write_report
from .prompt_loader import render_prompt
from .supabase_reader import SupabaseReader


SYSTEM_LABELS = {
    "masfactory": ("MASFactory System A", "A"),
    "hermes": ("Hermes-pattern System B", "B"),
}


def generate_weekly_system(*, settings: Settings, system: str) -> dict:
    if system not in SYSTEM_LABELS:
        raise ValueError(f"unknown system: {system}")
    label, letter = SYSTEM_LABELS[system]

    reader = SupabaseReader(settings)
    this_week = reader.weekly_snapshot(system=system)

    # Previous week (offset by 7 days) — fetch then compute summary
    until_prev = datetime.now(timezone.utc) - timedelta(days=7)
    since_prev = until_prev - timedelta(days=7)
    runs_prev = reader.runs_in_window(system=system, since=since_prev, until=until_prev)
    sigs_prev = reader.signals_for_runs([r["id"] for r in runs_prev])
    toks_prev = reader.token_usage_for_runs([r["id"] for r in runs_prev])
    from .supabase_reader import _summarise  # private helper, fine here
    prev_summary = _summarise(runs_prev, sigs_prev, toks_prev, this_week["actors_by_slug"])

    now = datetime.now(timezone.utc)
    iso_week = now.strftime("%G-W%V")

    prompt = render_prompt("weekly_system", system_label=label, system_letter=letter, iso_week=iso_week)
    user_payload = {
        "system_label": label,
        "system_letter": letter,
        "iso_week": iso_week,
        "this_week_summary": this_week["summary"],
        "previous_week_summary": prev_summary,
        "this_week_signals": _trim_signals(this_week["signals"]),
        "actor_names_by_slug": {s: a["name"] for s, a in this_week["actors_by_slug"].items()},
        "actor_categories_by_slug": {s: a["category"] for s, a in this_week["actors_by_slug"].items()},
    }

    client = OpenRouterClient(settings)
    body = client.chat(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        max_tokens=4096,
        temperature=0.4,
    )

    rel_dir = f"weekly/{iso_week}"
    filename = f"{system}.md"
    path = write_report(settings.reports_dir, rel_dir, filename, body)

    return {
        "path": path,
        "this_week_summary": this_week["summary"],
        "previous_week_summary": prev_summary,
        "tokens": {"input": client.tally.input_tokens, "output": client.tally.output_tokens, "calls": client.tally.calls},
    }


def _trim_signals(signals: list[dict], max_signals: int = 120) -> list[dict]:
    return [
        {k: s.get(k) for k in ("actor_slug", "dimension", "is_technical", "confidence", "title", "summary", "evidence_quote", "source_url", "source_kind", "inserted_at")}
        for s in signals[:max_signals]
    ]
