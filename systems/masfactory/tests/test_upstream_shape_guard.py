"""v0.4.42 — defensive guards against upstream shape drift.

The Classifier on Nemotron 3 Ultra 550B has been observed emitting individual
signals as JSON-encoded strings inside its `classified` list instead of parsed
dicts. Pre-v0.4.42 this crashed both AccumulateActor (loop_nodes.py) and
Persistence (persistence.py) with AttributeError: 'str' object has no
attribute 'get' and no audit was written for the run.

These tests exercise the guard at both nodes, confirming: (a) dict inputs
pass through unchanged, (b) JSON-string dicts are recovered, (c) unparseable
strings and non-dict / non-str objects are dropped to the audit log rather
than crashing the run.
"""
from __future__ import annotations

import json

from masfactory_system.agents.loop_nodes import _accumulate_actor
from masfactory_system.agents.persistence import _persist


# --------------------------------------------------------------------------
# Test fixtures
# --------------------------------------------------------------------------
def _classified_json(*items) -> str:
    """Wrap items into the {classified: [...]} JSON envelope the Classifier
    node emits."""
    return json.dumps({"classified": list(items)})


def _critique_json(*decisions) -> str:
    return json.dumps({"decisions": list(decisions)})


_GOOD_SIGNAL = {
    "actor_slug": "eth-zurich",
    "source_url": "https://ethz.ch/news/example",
    "dimension": "patents",
    "title": "Example patent filing",
    "summary": "Example summary of a patent filing at ETH Zurich.",
    "evidence_quote": "ETH Zurich has filed a new patent...",
    "confidence": 0.85,
}


# --------------------------------------------------------------------------
# AccumulateActor (loop_nodes.py) guard tests
# --------------------------------------------------------------------------
def test_accumulate_actor_dict_input_passes_through() -> None:
    """Baseline: dict signals reach `all_surviving_signals` unchanged."""
    attrs = {
        "current_actor_slug": "eth-zurich",
        "classified_json": _classified_json(_GOOD_SIGNAL),
        "critique_json": _critique_json({"signal_index": 0, "keep": True}),
    }
    out = _accumulate_actor({}, attrs)
    assert len(out["all_surviving_signals"]) == 1
    assert out["all_surviving_signals"][0]["actor_slug"] == "eth-zurich"
    assert out["dropped_cross_actor"] == []


def test_accumulate_actor_json_string_signal_is_recovered() -> None:
    """A signal arriving as a JSON-encoded string should be decoded back to
    a dict and passed through — the pre-v0.4.42 root-cause pattern."""
    stringified = json.dumps(_GOOD_SIGNAL)
    attrs = {
        "current_actor_slug": "eth-zurich",
        "classified_json": _classified_json(stringified),
        "critique_json": _critique_json({"signal_index": 0, "keep": True}),
    }
    out = _accumulate_actor({}, attrs)
    assert len(out["all_surviving_signals"]) == 1
    assert out["all_surviving_signals"][0]["actor_slug"] == "eth-zurich"
    assert out["dropped_cross_actor"] == []


def test_accumulate_actor_unparseable_string_dropped_not_raised() -> None:
    """A raw text signal that isn't JSON should be dropped to
    dropped_cross_actor with a diagnostic entry, not crash the run."""
    attrs = {
        "current_actor_slug": "eth-zurich",
        "classified_json": _classified_json("this is not JSON at all"),
        "critique_json": _critique_json({"signal_index": 0, "keep": True}),
    }
    out = _accumulate_actor({}, attrs)
    assert out["all_surviving_signals"] == []
    assert len(out["dropped_cross_actor"]) == 1
    drop = out["dropped_cross_actor"][0]
    assert "upstream shape" in drop["reason"]


def test_accumulate_actor_json_string_that_decodes_to_list_dropped() -> None:
    """A JSON string that decodes to a non-dict (e.g. a list) is dropped."""
    stringified_list = json.dumps(["still", "not", "a", "dict"])
    attrs = {
        "current_actor_slug": "eth-zurich",
        "classified_json": _classified_json(stringified_list),
        "critique_json": _critique_json({"signal_index": 0, "keep": True}),
    }
    out = _accumulate_actor({}, attrs)
    assert out["all_surviving_signals"] == []
    assert len(out["dropped_cross_actor"]) == 1
    assert out["dropped_cross_actor"][0]["type"] == "list"


def test_accumulate_actor_mixed_batch_recovers_partial() -> None:
    """A batch with 3 items — good dict, JSON-string dict, garbage — should
    yield 2 surviving signals and 1 drop, not crash."""
    stringified = json.dumps({
        **_GOOD_SIGNAL,
        "source_url": "https://ethz.ch/news/other",
    })
    good_2 = {**_GOOD_SIGNAL, "source_url": "https://ethz.ch/news/third"}
    attrs = {
        "current_actor_slug": "eth-zurich",
        "classified_json": _classified_json(_GOOD_SIGNAL, stringified, good_2, "garbage text"),
        "critique_json": _critique_json(
            {"signal_index": 0, "keep": True},
            {"signal_index": 1, "keep": True},
            {"signal_index": 2, "keep": True},
        ),
    }
    out = _accumulate_actor({}, attrs)
    assert len(out["all_surviving_signals"]) == 3
    # The "garbage text" item is dropped with an upstream-shape reason.
    upstream_drops = [d for d in out["dropped_cross_actor"] if "upstream shape" in d.get("reason", "")]
    assert len(upstream_drops) == 1


# --------------------------------------------------------------------------
# Persistence (persistence.py) guard tests
# --------------------------------------------------------------------------
class _RecordingAudit:
    """Captures writes so we can assert dropped_upstream_shape.json is produced."""
    def __init__(self) -> None:
        self.writes: dict[str, object] = {}

    def write_json(self, name: str, payload: object) -> None:
        self.writes[name] = payload


def test_persistence_json_string_signal_is_recovered() -> None:
    """When AccumulateActor upstream fails to convert (e.g. a future variant
    of the bug), Persistence's own guard still recovers JSON-string dicts."""
    stringified = json.dumps(_GOOD_SIGNAL)
    audit = _RecordingAudit()
    attrs = {
        "all_classified": [_GOOD_SIGNAL],
        "all_surviving_signals": [stringified],  # accumulator handed a str through
        "documents": [{"actor_slug": "eth-zurich", "source_url": _GOOD_SIGNAL["source_url"]}],
        "audit_folder": audit,
        "store": None,
        "run_id": "test-run",
    }
    _persist({}, attrs)
    # signals.json should contain the recovered dict
    assert len(audit.writes["signals.json"]) == 1
    assert audit.writes["signals.json"][0]["actor_slug"] == "eth-zurich"


def test_persistence_non_dict_non_str_dropped_to_audit() -> None:
    """None / int / other unexpected types should be dropped to
    dropped_upstream_shape.json rather than crash."""
    audit = _RecordingAudit()
    attrs = {
        "all_classified": [_GOOD_SIGNAL],
        "all_surviving_signals": [None, 42, _GOOD_SIGNAL],
        "documents": [{"actor_slug": "eth-zurich", "source_url": _GOOD_SIGNAL["source_url"]}],
        "audit_folder": audit,
        "store": None,
        "run_id": "test-run",
    }
    _persist({}, attrs)
    assert len(audit.writes["signals.json"]) == 1  # only the good dict
    drops = audit.writes["dropped_upstream_shape.json"]
    assert len(drops) == 2
    assert {d["type"] for d in drops} == {"NoneType", "int"}


def test_persistence_dict_only_input_produces_no_upstream_shape_audit() -> None:
    """Baseline: when everything is already a dict, no audit entry is written."""
    audit = _RecordingAudit()
    attrs = {
        "all_classified": [_GOOD_SIGNAL],
        "all_surviving_signals": [_GOOD_SIGNAL],
        "documents": [{"actor_slug": "eth-zurich", "source_url": _GOOD_SIGNAL["source_url"]}],
        "audit_folder": audit,
        "store": None,
        "run_id": "test-run",
    }
    _persist({}, attrs)
    assert "dropped_upstream_shape.json" not in audit.writes
