"""Browse the markdown reports the reports container has written."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from dashboard_app import data_access as da


st.set_page_config(page_title="Reports browser", layout="wide")
st.title("Reports browser")

reports_root = Path(da.reports_dir())
if not reports_root.exists():
    st.warning(f"Reports directory does not exist yet: {reports_root}")
    st.stop()

kind = st.radio("Report kind", options=["daily", "weekly", "thesis"], horizontal=True)
folder = reports_root / kind
if not folder.exists():
    st.info(f"No `{kind}` reports written yet.")
    st.stop()

# List periods (date subdirs)
periods = sorted([p for p in folder.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
if not periods:
    st.info(f"No `{kind}` reports written yet.")
    st.stop()

picked_period = st.selectbox("Period", periods, format_func=lambda p: p.name)
files = sorted(picked_period.glob("*.md"))
if not files:
    st.info("No markdown files in this period.")
    st.stop()

picked_file = st.selectbox("File", files, format_func=lambda f: f.name)
st.markdown("---")
st.caption(f"{picked_file.relative_to(reports_root)}")
st.markdown(picked_file.read_text(encoding="utf-8"))
