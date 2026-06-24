"""Daily report generator.

Pulls the last 24h of activity for one system from Supabase, feeds it to the
LLM with the daily-report prompt, writes the resulting markdown to
data/reports/daily/<YYYY-MM-DD>/<system>.md.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .openrouter import OpenRouterClient
from .output_writer import write_report
from .prompt_loader import render_prompt
from .supabase_reader import SupabaseReader


_ZURICH = ZoneInfo("Europe/Zurich")


SYSTEM_LABELS = {
    "masfactory": ("MASFactory System A", "A"),
    "hermes": ("Hermes System B", "B"),
}


def generate_daily(*, settings: Settings, system: str) -> dict:
    if system not in SYSTEM_LABELS:
        raise ValueError(f"unknown system: {system}")
    label, letter = SYSTEM_LABELS[system]

    reader = SupabaseReader(settings)
    snapshot = reader.daily_snapshot(system=system, window_hours=24)

    now = datetime.now(_ZURICH)
    date_iso = now.strftime("%Y-%m-%d")  # CET / CEST date — matches when the cron fired

    prompt = render_prompt("daily", system_label=label, system_letter=letter, date_iso=date_iso)
    user_payload = {
        "system_label": label,
        "system_letter": letter,
        "date_iso": date_iso,
        "summary": snapshot["summary"],
        "signals": _trim_signals(snapshot["signals"]),
        "actor_names_by_slug": {s: a["name"] for s, a in snapshot["actors_by_slug"].items()},
    }

    client = OpenRouterClient(settings)
    body = client.chat(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        max_tokens=2048,
        temperature=0.3,
    )

    rel_dir = f"daily/{date_iso}"
    filename = f"{system}.md"
    path = write_report(settings.reports_dir, rel_dir, filename, body)

    return {
        "path": path,
        "snapshot_summary": snapshot["summary"],
        "tokens": {"input": client.tally.input_tokens, "output": client.tally.output_tokens, "calls": client.tally.calls},
    }


def _trim_signals(signals: list[dict], max_signals: int = 50) -> list[dict]:
    """Cap signals shipped to the LLM so daily reports stay bounded.

    v0.4.27: includes the v0.4.0 Ehrenthal signal_type, v0.4.19 defense
    flags, v0.4.24 sentiment_label, and the stakeholder lens. Without
    these, the LLM writing the report has no idea what categories the
    classification scheme even uses — which made every prior daily report
    silent on the four-signal mix the thesis is built on.
    """
    keys = (
        "actor_slug", "dimension", "signal_type", "is_technical", "confidence",
        "title", "summary", "evidence_quote", "source_url", "source_kind",
        "stakeholder", "sentiment_label", "sentiment_score",
        "defense_engagement", "defense_ambivalence",
    )
    return [{k: s.get(k) for k in keys} for s in signals[:max_signals]]
