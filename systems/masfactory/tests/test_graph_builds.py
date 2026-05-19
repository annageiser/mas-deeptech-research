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
