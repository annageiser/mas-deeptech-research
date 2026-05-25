"""Smoke tests for System B — no network, no credentials."""

from __future__ import annotations

import os
import tempfile

import pytest

from hermes_system.config import ConfigError, load_settings
from hermes_system.memory import MemoryManager
from hermes_system.skills_loader import SkillsLoader
from hermes_system.tools_registry import ToolsRegistry


SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


def test_settings_require_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_settings(require_supabase=False)


def test_settings_minimum(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    s = load_settings(require_supabase=False)
    assert s.openrouter_api_key == "test"
    assert s.model_main.startswith("nvidia/nemotron")
    assert not s.has_supabase


def test_all_four_skills_discovered():
    loaded = SkillsLoader(SKILLS_DIR).discover()
    names = sorted(s.name for s in loaded)
    assert names == ["arxiv", "parallel-cli", "research-paper-writing", "scrapling"]


def test_skill_prompt_block_is_non_empty():
    loaded = SkillsLoader(SKILLS_DIR).discover()
    for skill in loaded:
        block = skill.to_prompt_block()
        assert skill.name in block
        assert "When to use" in block or "Procedure" in block


def test_memory_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "mem.sqlite")
        mem = MemoryManager(db)
        mem.set_preference("classification_priority", "technical_first")
        assert mem.list_preferences() == [("classification_priority", "technical_first")]
        mem.record_procedure(
            actor_slug="eth-zurich-quantum-center",
            summary="Found 3 arXiv papers and 1 partnership announcement.",
            successful_sources=["arxiv", "website"],
            common_signal_dimensions=["research_output", "partnership_or_alliance"],
        )
        recalled = mem.recall_procedure("eth-zurich-quantum-center")
        assert len(recalled) == 1
        assert recalled[0]["successful_sources"] == ["arxiv", "website"]


def test_tools_registry_lists_four_tools():
    reg = ToolsRegistry()
    from hermes_system.tools_registry import register_default_tools

    buffer: list[dict] = []
    register_default_tools(reg, actor_slug="test", signal_buffer=buffer)
    names = sorted(t.name for t in reg.list())
    assert names == ["arxiv_search", "finish_actor", "news_search", "register_signal", "website_fetch"]
