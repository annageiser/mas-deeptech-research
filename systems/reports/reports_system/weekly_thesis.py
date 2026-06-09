"""Weekly thesis progress report generator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .git_history import git_log_since, read_thesis_notes
from .openrouter import OpenRouterClient
from .output_writer import write_report
from .prompt_loader import render_prompt
from .supabase_reader import SupabaseReader


_ZURICH = ZoneInfo("Europe/Zurich")


def generate_weekly_thesis(*, settings: Settings) -> dict:
    reader = SupabaseReader(settings)
    both = reader.both_systems_summary(window_hours=24 * 7)
    commits = git_log_since(repo_dir=settings.repo_dir, days=7)
    notes = read_thesis_notes(settings.thesis_notes_path)

    now = datetime.now(_ZURICH)
    iso_week = now.strftime("%G-W%V")

    prompt = render_prompt("weekly_thesis", iso_week=iso_week)
    user_payload = {
        "iso_week": iso_week,
        "both_systems_summary": both,
        "commits_last_7_days": commits,
        "thesis_notes": notes or "(no notes file present this week)",
    }

    client = OpenRouterClient(settings)
    body = client.chat(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        max_tokens=8192,  # v0.4.3 — reports were getting truncated at 4096
        temperature=0.4,
    )

    rel_dir = f"thesis/{iso_week}"
    filename = "progress.md"
    path = write_report(settings.reports_dir, rel_dir, filename, body)

    return {
        "path": path,
        "commit_count": len(commits),
        "both_systems_summary": both,
        "tokens": {"input": client.tally.input_tokens, "output": client.tally.output_tokens, "calls": client.tally.calls},
    }
