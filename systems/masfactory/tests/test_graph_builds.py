"""Smoke tests — run without network or credentials.

These are what the Dockerfile's `RUN python -m masfactory_system.runner build-check`
step relies on: if the graph won't compile, the image will not build.
"""

from __future__ import annotations

import pytest

from masfactory import Agent, template_defaults_for

from masfactory_system.classification import load_schema, schema_as_prompt_block
from masfactory_system.config import ConfigError, load_settings
from masfactory_system.graph import build_graph
from masfactory_system.runner import _StubModel
from masfactory_system.schema import Actor


def test_graph_compiles_with_stub_model():
    with template_defaults_for(type_filter=Agent, model=_StubModel()):
        graph = build_graph()
        graph.build()
    assert graph.name == "masfactory_swiss_quantum"


def test_graph_instantiation_without_build():
    """Even without a model, constructing the RootGraph itself should succeed."""
    graph = build_graph()
    assert graph.name == "masfactory_swiss_quantum"


def test_schema_loads_and_renders():
    schema = load_schema()
    assert "dimensions" in schema
    assert len(schema["dimensions"]) >= 5
    block = schema_as_prompt_block()
    assert "technical" in block.lower()


def test_actor_model_validates_minimum():
    actor = Actor(slug="x", name="X", category="university_or_research_hub")
    assert actor.slug == "x"


def test_settings_require_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_settings(require_supabase=False)


def test_settings_load_with_minimum(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    settings = load_settings(require_supabase=False)
    assert settings.openrouter_api_key == "test-key"
    assert settings.model_main.startswith("nvidia/nemotron")
    assert not settings.has_supabase


# ---------- per-actor Loop unit tests ----------

def test_actor_loop_done():
    from masfactory_system.agents.loop_nodes import actor_loop_done
    assert actor_loop_done({}, {"documents_by_actor": [], "actor_loop_index": 0}) is True
    assert actor_loop_done({}, {"documents_by_actor": [{"actor_slug": "x"}], "actor_loop_index": 0}) is False
    assert actor_loop_done({}, {"documents_by_actor": [{"actor_slug": "x"}], "actor_loop_index": 1}) is True


def test_prepare_current_actor_picks_index():
    from masfactory_system.agents.loop_nodes import _prepare_current_actor
    docs_by_actor = [
        {"actor_slug": "a1", "documents": [{"source_url": "u1", "actor_slug": "a1"}]},
        {"actor_slug": "a2", "documents": [{"source_url": "u2", "actor_slug": "a2"}, {"source_url": "u3", "actor_slug": "a2"}]},
    ]
    out = _prepare_current_actor({}, {"documents_by_actor": docs_by_actor, "actor_loop_index": 1})
    assert out["current_actor_slug"] == "a2"
    assert out["current_actor_doc_count"] == 2
    # Scratch keys cleared
    assert out["candidates_json"] == ""
    assert out["classified_json"] == ""
    assert out["critique_json"] == ""


def test_accumulate_actor_appends_and_filters_cross_attribution():
    import json
    from masfactory_system.agents.loop_nodes import _accumulate_actor

    # Iteration's classified contains 2 valid + 1 misattributed signal.
    classified_payload = {
        "classified": [
            {"actor_slug": "a1", "source_url": "u1", "dimension": "research_output", "is_technical": True, "confidence": 0.8},
            {"actor_slug": "a2", "source_url": "u-wrong", "dimension": "funding_or_grant", "is_technical": False, "confidence": 0.9},  # misattributed
            {"actor_slug": "a1", "source_url": "u2", "dimension": "partnership_or_alliance", "is_technical": False, "confidence": 0.6},
        ]
    }
    critique_payload = {
        "decisions": [
            {"signal_index": 0, "keep": True},
            {"signal_index": 1, "keep": True},
            {"signal_index": 2, "keep": False},
        ]
    }
    attrs = {
        "current_actor_slug": "a1",
        "classified_json": json.dumps(classified_payload),
        "critique_json": json.dumps(critique_payload),
        "all_classified": [],
        "all_critique": [],
        "all_surviving_signals": [],
        "dropped_cross_actor": [],
        "actor_loop_index": 0,
    }
    out = _accumulate_actor({}, attrs)
    # Misattribution dropped
    assert len(out["dropped_cross_actor"]) == 1
    assert out["dropped_cross_actor"][0]["expected"] == "a1"
    assert out["dropped_cross_actor"][0]["got"] == "a2"
    # 2 classified appended (the 1 misattributed one dropped before accumulation)
    assert len(out["all_classified"]) == 2
    # 1 critique decision survives the re-indexing (the kept=True a1 signal)
    assert len(out["all_critique"]) == 2
    # Only signal_index=0 was kept (with critique remap); index=2 was kept=False
    assert len(out["all_surviving_signals"]) == 1
    assert out["actor_loop_index"] == 1
    # surviving_signals_json promoted for Analyst
    surviving = json.loads(out["surviving_signals_json"])
    assert len(surviving) == 1
    assert surviving[0]["actor_slug"] == "a1"
