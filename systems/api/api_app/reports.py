"""Reads the markdown reports the reports container writes to data/reports/."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

from .config import load_settings


KINDS = ("daily", "weekly", "thesis")


def _root() -> str:
    return load_settings().reports_dir


def list_reports(kind: Optional[str] = None) -> list[dict]:
    root = _root()
    out: list[dict] = []
    kinds = [kind] if kind in KINDS else list(KINDS)
    for k in kinds:
        kdir = os.path.join(root, k)
        if not os.path.isdir(kdir):
            continue
        for period in sorted(os.listdir(kdir), reverse=True):
            pdir = os.path.join(kdir, period)
            if not os.path.isdir(pdir):
                continue
            for fname in sorted(os.listdir(pdir)):
                if not fname.endswith(".md"):
                    continue
                out.append({
                    "kind": k,
                    "period": period,
                    "file": fname,
                    "title": _pretty(k, period, fname),
                })
    return out


def get_report(kind: str, period: str, file: str) -> Optional[str]:
    # Guard against path traversal.
    for part in (kind, period, file):
        if "/" in part or ".." in part or "\\" in part:
            return None
    path = os.path.join(_root(), kind, period, file)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _pretty(kind: str, period: str, fname: str) -> str:
    stem = fname[:-3] if fname.endswith(".md") else fname
    who = {"masfactory": "System A", "hermes": "System B", "progress": "Thesis progress"}.get(stem, stem.title())
    if kind == "daily":
        return f"{who} — {period}"
    m = re.match(r"(\d{4})-W(\d{2})", period)
    if m:
        try:
            monday = datetime.fromisocalendar(int(m.group(1)), int(m.group(2)), 1).date()
            return f"{who} — week {m.group(2)} {m.group(1)} (from {monday.isoformat()})"
        except Exception:
            pass
    return f"{who} — {period}"
