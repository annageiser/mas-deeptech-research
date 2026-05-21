"""Git log reader for the thesis weekly report.

Run as `git -C <repo_dir> log --since=...`. Falls back gracefully if the
repo directory isn't a git checkout (e.g. when run from a fresh container
without the repo bind-mounted).
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional


def git_log_since(*, repo_dir: str, days: int = 7) -> list[dict]:
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    # Use a record separator that's unlikely to appear in commit messages.
    sep = "\x1f"
    fmt = sep.join(["%H", "%an", "%ad", "%s"])

    try:
        out = subprocess.check_output(
            [
                "git",
                "-C",
                repo_dir,
                "log",
                f"--since={since}",
                f"--pretty=format:{fmt}%n--BODY-START--%n%b%n--BODY-END--",
                "--date=short",
            ],
            text=True,
            timeout=15,
        )
    except Exception:
        return []

    commits: list[dict] = []
    for chunk in out.split("--BODY-END--"):
        chunk = chunk.strip()
        if not chunk:
            continue
        head, _, body = chunk.partition("--BODY-START--")
        head_parts = head.strip().split(sep)
        if len(head_parts) < 4:
            continue
        commits.append(
            {
                "sha": head_parts[0],
                "author": head_parts[1],
                "date": head_parts[2],
                "subject": head_parts[3],
                "body": body.strip(),
            }
        )
    return commits


def read_thesis_notes(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None
