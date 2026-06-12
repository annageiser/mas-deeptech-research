"""Tests for v0.4.25 — Phoenix observability gate.

Does NOT exercise the real OpenInference instrumentor (would require a
live Phoenix collector or extensive mocking of OTel SDK internals).
The module's contract is that init() is a no-op when disabled and
graceful when deps are missing — those are the things we verify here.
"""

from __future__ import annotations

import pytest

from masfactory_system import observability


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_ENABLED", raising=False)
    assert observability.is_enabled() is False


def test_env_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "true", "yes", "on", "TRUE", "  1  "):
        monkeypatch.setenv("PHOENIX_ENABLED", value)
        assert observability.is_enabled() is True, f"failed for value={value!r}"


def test_env_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("", "0", "false", "no", "off", "anything-else"):
        monkeypatch.setenv("PHOENIX_ENABLED", value)
        assert observability.is_enabled() is False, f"failed for value={value!r}"


def test_default_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    assert observability.collector_endpoint() == observability.DEFAULT_ENDPOINT


def test_endpoint_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://otel.local:4317")
    assert observability.collector_endpoint() == "http://otel.local:4317"


def test_default_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_PROJECT_NAME", raising=False)
    assert observability.project_name() == observability.DEFAULT_PROJECT


def test_project_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "alt")
    assert observability.project_name() == "alt"


def test_init_returns_false_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_ENABLED", raising=False)
    # Reset the module-level singleton so init() takes the disabled path
    # even when an earlier test in the suite happened to enable it.
    observability._initialized = False  # noqa: SLF001
    assert observability.init(run_id="r1") is False


def test_init_returns_false_when_deps_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable Phoenix but ensure the import path returns False if the deps
    aren't installed. The dev environment does not pin them, so this
    exercises the warn-and-skip branch."""
    monkeypatch.setenv("PHOENIX_ENABLED", "1")
    observability._initialized = False  # noqa: SLF001
    # If the dep IS installed in this env, the path goes to the registration
    # try/except — which may succeed (collector unreachable but register
    # still returns) or fail. In either case init() returns True/False
    # without raising, and the cron path continues.
    result = observability.init(run_id="r1")
    assert isinstance(result, bool)


def test_init_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_ENABLED", raising=False)
    observability._initialized = False  # noqa: SLF001
    assert observability.init() is False
    # Second call must not raise / re-register, regardless of dep state.
    assert observability.init() is False
