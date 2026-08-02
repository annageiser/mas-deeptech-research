"""System A's retrieval budget must be one number per channel, and reachable.

Two defects motivated these tests.

FIRST, three sources disagreed about the same knobs. config.py defaulted arXiv
to 5 and website to 3 (the pre-v0.4.0 conservative values) while both
.env.example and the retriever fallbacks documented the wider v0.4.0 funnel of
10 and 5. Production had adopted the lowest set, so System A ran at roughly
half its documented design point on the two richest channels for research
actors. A budget asymmetry that is undocumented and below the system's own
stated design is a confound in the A-vs-B comparison, not a finding about
architecture.

SECOND, MASF_LIMIT_PRESS and MASF_LIMIT_PATENTS were documented in
.env.example but runner.py never passed them into the graph, so the retriever
always fell back to its own constants and the env vars did nothing at all.

These tests pin every source to the same numbers and prove the env vars now
reach the retriever.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import masfactory_system
from masfactory_system.config import load_settings
from masfactory_system.graph import WORKFLOW_ATTRIBUTES


PKG = Path(masfactory_system.__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
RETRIEVER = PKG / "agents" / "retriever.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# The documented v0.4.0 funnel.
EXPECTED = {
    "arxiv": 10,
    "website": 5,
    "news": 10,
    "press": 10,
    "patents": 10,
}


def _clear(monkeypatch):
    for key in ("MASF_LIMIT_ARXIV", "MASF_LIMIT_WEBSITE", "MASF_LIMIT_NEWS",
                "MASF_LIMIT_PRESS", "MASF_LIMIT_PATENTS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_settings_defaults_are_the_documented_funnel(monkeypatch):
    _clear(monkeypatch)
    s = load_settings(require_supabase=False)

    assert s.limit_arxiv_per_actor == EXPECTED["arxiv"]
    assert s.limit_website_pages_per_actor == EXPECTED["website"]
    assert s.limit_news_per_actor == EXPECTED["news"]
    assert s.limit_press_per_actor == EXPECTED["press"]
    assert s.limit_patents_per_actor == EXPECTED["patents"]


def test_graph_attribute_defaults_match_settings(monkeypatch):
    _clear(monkeypatch)
    s = load_settings(require_supabase=False)

    assert WORKFLOW_ATTRIBUTES["limit_arxiv_per_actor"] == s.limit_arxiv_per_actor
    assert WORKFLOW_ATTRIBUTES["limit_website_pages_per_actor"] == s.limit_website_pages_per_actor
    assert WORKFLOW_ATTRIBUTES["limit_news_per_actor"] == s.limit_news_per_actor
    assert WORKFLOW_ATTRIBUTES["limit_press_per_actor"] == s.limit_press_per_actor
    assert WORKFLOW_ATTRIBUTES["limit_patents_per_actor"] == s.limit_patents_per_actor


def test_retriever_fallbacks_match_too():
    """The retriever's own `attrs.get(..., N)` fallbacks are a fourth copy of
    these numbers. If they drift, a missing attribute silently changes the
    budget."""
    src = RETRIEVER.read_text(encoding="utf-8")
    found = dict(re.findall(r'attrs\.get\("limit_(\w+?)_per_actor", (\d+)\)', src))
    assert int(found["arxiv"]) == EXPECTED["arxiv"]
    assert int(found["news"]) == EXPECTED["news"]
    assert int(found["press"]) == EXPECTED["press"]
    assert int(found["patents"]) == EXPECTED["patents"]
    web = re.search(r'attrs\.get\("limit_website_pages_per_actor", (\d+)\)', src)
    assert web and int(web.group(1)) == EXPECTED["website"]


@pytest.mark.skipif(not ENV_EXAMPLE.is_file(), reason="outside a repo checkout")
def test_env_example_documents_the_same_numbers():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for channel, value in EXPECTED.items():
        m = re.search(rf"^MASF_LIMIT_{channel.upper()}=(\d+)", text, re.M)
        assert m, f".env.example does not document MASF_LIMIT_{channel.upper()}"
        assert int(m.group(1)) == value, (
            f".env.example says MASF_LIMIT_{channel.upper()}={m.group(1)}, code says {value}"
        )


@pytest.mark.parametrize("env_key,field", [
    ("MASF_LIMIT_ARXIV", "limit_arxiv_per_actor"),
    ("MASF_LIMIT_WEBSITE", "limit_website_pages_per_actor"),
    ("MASF_LIMIT_NEWS", "limit_news_per_actor"),
    ("MASF_LIMIT_PRESS", "limit_press_per_actor"),
    ("MASF_LIMIT_PATENTS", "limit_patents_per_actor"),
])
def test_each_env_var_is_actually_honoured(monkeypatch, env_key, field):
    _clear(monkeypatch)
    monkeypatch.setenv(env_key, "7")
    assert getattr(load_settings(require_supabase=False), field) == 7


def test_press_and_patents_reach_the_retriever(monkeypatch):
    """The specific regression: runner.py built the attribute dict without
    these two keys, so setting the env var changed nothing downstream."""
    _clear(monkeypatch)
    monkeypatch.setenv("MASF_LIMIT_PRESS", "3")
    monkeypatch.setenv("MASF_LIMIT_PATENTS", "4")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    settings = load_settings(require_supabase=True)

    runner_src = (PKG / "runner.py").read_text(encoding="utf-8")
    assert '"limit_press_per_actor": settings.limit_press_per_actor' in runner_src
    assert '"limit_patents_per_actor": settings.limit_patents_per_actor' in runner_src
    assert settings.limit_press_per_actor == 3
    assert settings.limit_patents_per_actor == 4
