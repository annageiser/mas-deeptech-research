"""Markdown file writer + small front-matter header.

Reports are markdown files with a YAML-ish header so a future dashboard can
filter by date / system / kind without re-parsing the body.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def write_report(reports_root: str, rel_dir: str, filename: str, body: str) -> str:
    dir_path = os.path.join(reports_root, rel_dir)
    os.makedirs(dir_path, exist_ok=True)
    full_path = os.path.join(dir_path, filename)

    header = (
        f"<!-- generated_at: {datetime.now(timezone.utc).isoformat()} -->\n"
        f"<!-- generator: reports_system (Container C) -->\n\n"
    )
    with open(full_path, "w", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(body.rstrip())
        fh.write("\n")
    return full_path
