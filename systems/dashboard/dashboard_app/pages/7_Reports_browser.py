"""Reports browser — daily + weekly markdown reports written by Container C."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from dashboard_app import data_access as da
from dashboard_app import labels as L


st.set_page_config(page_title="Reports", layout="wide", page_icon="📄")
st.title("📄 Reports")
st.caption(
    "Auto-generated narrative reports. Daily and per-system reports go out after each scrape. "
    "Weekly reports synthesise the whole week (one per system + one on thesis progress)."
)

reports_root = Path(da.reports_dir())
if not reports_root.exists():
    st.warning(f"Reports directory does not exist yet: {reports_root}")
    st.stop()

KIND_LABEL = {
    "daily":   "📅 Daily — per-system briefings",
    "weekly":  "📆 Weekly — per-system summaries",
    "thesis":  "🎓 Weekly — thesis progress",
}

# Only show kinds that have content
available_kinds = [k for k in KIND_LABEL if (reports_root / k).exists()]
if not available_kinds:
    st.info(
        "No reports written yet. They'll appear automatically once cron runs:\n"
        "- daily reports at 02:00 (System A) and 05:00 (System B) Europe/Zurich\n"
        "- weekly reports on Sundays at 08:00 Europe/Zurich"
    )
    st.stop()

kind = st.radio(
    "Report kind",
    options=available_kinds,
    format_func=lambda k: KIND_LABEL[k],
    horizontal=True,
)
folder = reports_root / kind

periods = sorted([p for p in folder.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
if not periods:
    st.info(f"No `{kind}` reports written yet.")
    st.stop()

def _period_pretty(p: Path) -> str:
    if kind == "daily":
        return p.name  # YYYY-MM-DD
    if kind == "weekly" or kind == "thesis":
        # ISO week format YYYY-Www
        m = re.match(r"(\d{4})-W(\d{2})", p.name)
        if m:
            year, week = int(m.group(1)), int(m.group(2))
            try:
                # Monday of that ISO week
                monday = datetime.fromisocalendar(year, week, 1).date()
                return f"Week {week}, {year} (starting {monday.isoformat()})"
            except Exception:
                pass
    return p.name


def _file_pretty(f: Path) -> str:
    stem = f.stem
    if stem in L.SYSTEM_SHORT.values() or stem in L.SYSTEM_LABEL:
        return L.system_label(stem)
    if stem == "masfactory":
        return L.system_label("masfactory")
    if stem == "hermes":
        return L.system_label("hermes")
    if stem == "progress":
        return "Thesis progress"
    return stem.replace("_", " ").title()


picked_period = st.selectbox("Period", periods, format_func=_period_pretty)
files = sorted(picked_period.glob("*.md"))
if not files:
    st.info("No markdown files in this period.")
    st.stop()

picked_file = st.selectbox("Report", files, format_func=_file_pretty)
st.markdown("---")
st.caption(f"_{picked_file.relative_to(reports_root)}_")
st.markdown(picked_file.read_text(encoding="utf-8"))
