"""Per-run audit folder writer.

Every `g.invoke()` gets a folder under `MASF_AUDIT_DIR` (defaults to
/data/raw/runs). The Supabase tables are the authoritative store, but the
on-disk audit folder is the artefact the thesis cites for reproducibility:
prompts, raw outputs, token tallies, and final brief land here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


@dataclass
class AuditFolder:
    root: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, base_dir: str) -> "AuditFolder":
        root = os.path.join(base_dir, _ts_now())
        os.makedirs(os.path.join(root, "raw_docs"), exist_ok=True)
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

    def write_raw_doc(self, slug: str, body: str) -> str:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slug)
        path = os.path.join(self.root, "raw_docs", f"{safe}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path
