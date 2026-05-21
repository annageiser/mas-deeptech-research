"""Per-run audit folder (System B variant).

Same shape as System A's `data/raw/runs/<iso-ts>/`, with a `system: 'hermes'`
marker file so it's easy to tell which folders belong to which system when
both are running.

Timestamps in Europe/Zurich (CET/CEST) to match cron-firing time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


_ZURICH = ZoneInfo("Europe/Zurich")


def _ts_now() -> str:
    return datetime.now(_ZURICH).strftime("%Y-%m-%dT%H-%M-%S%z")


@dataclass
class AuditFolder:
    root: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, base_dir: str) -> "AuditFolder":
        root = os.path.join(base_dir, f"{_ts_now()}__hermes")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "system.txt"), "w", encoding="utf-8") as fh:
            fh.write("hermes\n")
        return cls(root=root)

    def write_json(self, name: str, payload: Any) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        return path

    def write_text(self, name: str, text: str) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path
