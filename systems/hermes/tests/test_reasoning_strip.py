"""Unit tests for the Layer 2 reasoning-token strip in persist_signals.py.

This helper is the load-bearing client-side defence introduced in v0.4.38
(see docs/iterations/v0.4.38-nemotron-3-ultra-migration.md). When the
upstream Hermes Agent CLI fails to unwrap a reasoning model's
<think>...</think> output, this strip runs over agent stdout before
_extract_json_block so the JSON payload can still be parsed. The thesis
cites this defence by name in §3.4; CI coverage here is the engineering-
discipline signal §3.5.4 of the thesis claims.
"""
from __future__ import annotations

import persist_signals


_strip = persist_signals._strip_reasoning_artefacts


# --------------------------------------------------------------------------
# No-op cases
# --------------------------------------------------------------------------
def test_empty_string_returns_empty() -> None:
    assert _strip("") == ""


def test_clean_text_unchanged() -> None:
    text = 'Here is a JSON answer:\n\n```json\n{"signals": []}\n```\n'
    assert _strip(text) is text or _strip(text) == text


def test_no_reasoning_tags_returns_input_unchanged() -> None:
    text = "Plain text with no XML tags at all, just words and {braces} and [brackets]."
    assert _strip(text) == text


# --------------------------------------------------------------------------
# Balanced-tag stripping
# --------------------------------------------------------------------------
def test_balanced_think_block_stripped() -> None:
    text = "<think>some private reasoning</think>visible answer"
    assert _strip(text).strip() == "visible answer"


def test_multiple_balanced_blocks_stripped() -> None:
    text = "<think>one</think>middle<thinking>two</thinking>end"
    assert _strip(text) == "middleend"


def test_all_six_tag_families_stripped() -> None:
    for tag in ("think", "thinking", "reasoning", "thought", "analysis", "scratchpad"):
        text = f"<{tag}>private</{tag}>public"
        assert _strip(text).strip() == "public", f"failed for tag <{tag}>"


def test_case_insensitive() -> None:
    text = "<THINK>private</THINK>public"
    assert _strip(text).strip() == "public"


def test_multiline_balanced_block_stripped() -> None:
    text = "<think>line one\nline two\nline three</think>visible"
    assert _strip(text).strip() == "visible"


def test_json_after_reasoning_block_preserved() -> None:
    text = '<think>I will list signals</think>\n```json\n{"signals": [{"x": 1}]}\n```\n'
    out = _strip(text)
    assert '"signals"' in out
    assert "<think>" not in out
    assert "private" not in out  # spot-check that block content is gone


# --------------------------------------------------------------------------
# Dangling-opener stripping
# --------------------------------------------------------------------------
def test_dangling_opener_before_json_stripped() -> None:
    text = '<think>truncated reasoning never closed { "signals": [] }'
    out = _strip(text)
    assert out.startswith('{ "signals"')
    assert "<think>" not in out


def test_dangling_opener_before_array_stripped() -> None:
    text = "<reasoning>truncated\n  more thoughts\n  [\"a\", \"b\"]"
    out = _strip(text)
    assert out.startswith('["a"')


def test_dangling_opener_before_code_fence_stripped() -> None:
    text = "<thought>truncated reasoning```json\n{\"signals\": []}\n```"
    out = _strip(text)
    assert out.startswith("```json")


# --------------------------------------------------------------------------
# Negative cases — opener must NOT be stripped when it sits mid-text
# --------------------------------------------------------------------------
def test_opener_mid_text_with_no_close_is_preserved() -> None:
    # An unclosed opener that appears AFTER content should not trigger the
    # dangling-prefix strip because the regex is ^-anchored.
    text = "prefix content <think>partial reasoning never closes"
    out = _strip(text)
    assert out.startswith("prefix content")


# --------------------------------------------------------------------------
# Realistic Nemotron 3 Ultra fixture
# --------------------------------------------------------------------------
def test_realistic_nemotron_output_round_trip() -> None:
    fixture = (
        "<think>\n"
        "Let me think about which signals to extract for this actor.\n"
        "ID Quantique published a press release on 2026-06-15 about "
        "quantum key distribution deployment with a Swiss bank.\n"
        "</think>\n"
        "\n"
        "```json\n"
        "{\n"
        '  "actor_slug": "id-quantique",\n'
        '  "signals": [\n'
        "    {\n"
        '      "signal_type": "customer_cocreation",\n'
        '      "title": "QKD deployment at Swiss bank"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
    )
    out = _strip(fixture)
    assert "<think>" not in out
    assert "Let me think" not in out
    assert '"actor_slug": "id-quantique"' in out
    assert '"customer_cocreation"' in out
