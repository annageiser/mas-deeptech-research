"""Map the project's signal taxonomy (schema.yaml) to a REFI-QDA codebook.

REFI-QDA represents codes as a tree under <CodeBook><Codes>. Each
<Code> has a guid + name + optional description + nested <Code>
children for hierarchy.

We render the codebook as:

  Categories (top-level, 4):
    - Legitimacy
    - Customer co-creation
    - Community ecosystem
    - Future trajectory

  Under each category: the dimensions of that signal_type (19 total
  across the 4 categories), exactly matching the v0.4.0 taxonomy.

  Cross-cutting (siblings of the four categories, not nested under any
  one signal_type because they layer ON TOP of a signal_type per v0.4.19):
    - Defense engagement
    - Defense ambivalence

  Quality flags (used by the gold-set protocol — distinct from signal_type
  / dimension classification):
    - Keep (signal worth keeping at all?)
    - Drop (signal should not be in the corpus)
    - Actor attribution correct
    - Actor attribution wrong

Coders apply EXACTLY ONE signal_type code, EXACTLY ONE dimension code
(within that signal_type's children), zero or more defense flags, and
EXACTLY ONE keep/drop + actor-attribution-quality code.

This matches the gold-set YAML schema in
`data/gold/labels.yaml.example`.

The codebook is read from `schema.yaml` so it stays in sync with the
runtime classifier prompts and the migrations history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Stable namespace so re-running the codebook generator produces the
# same code GUIDs for the same code name. REFI-QDA tools expect GUIDs
# to be stable across exports for the same conceptual code.
_GUID_NS = uuid.UUID("8c4f3f1e-5c8b-4f6c-b1d7-2f9e0c1a4b3e")


def _stable_guid(name: str) -> str:
    """Deterministic UUIDv5 — same name → same GUID across exports."""
    return str(uuid.uuid5(_GUID_NS, name))


@dataclass
class CodeNode:
    """A single REFI-QDA Code entry. Children form the hierarchy."""

    guid: str
    name: str
    description: str = ""
    children: list["CodeNode"] = field(default_factory=list)
    # When True the code is a quality flag (keep / actor-correct) rather
    # than part of the signal taxonomy. Renderer treats them identically
    # in the XML but the importer needs to know which axis a code lives on.
    axis: str = "dimension"  # 'signal_type' | 'dimension' | 'defense_flag' | 'quality_flag'


@dataclass
class CodeBook:
    codes: list[CodeNode]
    # Flat lookup: name → CodeNode for the importer. Includes all
    # nested codes.
    by_name: dict[str, CodeNode] = field(default_factory=dict)

    def all_nodes(self) -> list[CodeNode]:
        out: list[CodeNode] = []
        stack = list(self.codes)
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(n.children)
        return out


# Display names — kept stable so coded .qdpx files round-trip cleanly
# even if schema.yaml's `label` field is edited for the dashboard.
SIGNAL_TYPE_DISPLAY = {
    "legitimacy": "Legitimacy",
    "customer_cocreation": "Customer co-creation",
    "community_ecosystem": "Community ecosystem",
    "future_trajectory": "Future trajectory",
}

DEFENSE_FLAGS = (
    ("defense_engagement", "Defense engagement",
     "Set when the signal explicitly mentions defense / national-security "
     "customer wins, dual-use programmes, NATO / AFCEA / DARPA mentions, "
     "ITAR / EAR relevance, or other explicit defense-sector engagement. "
     "Layered ON TOP OF a signal_type (per v0.4.19)."),
    ("defense_ambivalence", "Defense ambivalence",
     "Set when the actor publicly *withholds* information citing national "
     "security / export controls, OR distances itself from defense uses "
     "while accepting defense funding."),
)

QUALITY_FLAGS = (
    ("gold_keep_true", "Keep — worth keeping",
     "The signal is on-topic, well-attributed, and the dimension is "
     "defensible. The Critic should have kept it."),
    ("gold_keep_false", "Drop — should have been filtered",
     "The signal is off-topic, low-quality, marketing-only, or otherwise "
     "should not have survived the Critic."),
    ("gold_actor_correct", "Actor attribution correct",
     "The actor_slug attribution is right."),
    ("gold_actor_wrong", "Actor attribution wrong",
     "The signal is about a different actor — the system mis-attributed."),
)


def build_codebook(schema_path: str | Path) -> CodeBook:
    """Read the signal taxonomy from schema.yaml and render a CodeBook.

    Only fields the importer needs are read: signal_types, dimensions,
    and the dimension→signal_type membership (via dimension.signal_type).
    """
    raw = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8")) or {}

    # ---- Build the four signal_type top-level nodes ----
    signal_type_nodes: dict[str, CodeNode] = {}
    for st in raw.get("signal_types") or []:
        key = st["key"]
        display = SIGNAL_TYPE_DISPLAY.get(key, st.get("label") or key)
        signal_type_nodes[key] = CodeNode(
            guid=_stable_guid(f"signal_type:{key}"),
            name=display,
            description=(st.get("description") or "").strip(),
            axis="signal_type",
        )

    # ---- Nest each dimension under its signal_type ----
    for dim in raw.get("dimensions") or []:
        key = dim["key"]
        parent_key = dim.get("signal_type")
        parent = signal_type_nodes.get(parent_key)
        if parent is None:
            # Should not happen on a valid schema, but stay tolerant.
            continue
        parent.children.append(
            CodeNode(
                guid=_stable_guid(f"dimension:{key}"),
                # Use the v0.4.0 dimension key as the code name — keeps
                # the importer's mapping a direct string compare.
                name=key,
                description=(dim.get("description") or "").strip(),
                axis="dimension",
            )
        )

    # ---- Defense flag siblings ----
    defense_root = CodeNode(
        guid=_stable_guid("defense_flags_root"),
        name="Defense flags",
        description="Boolean flags layered on top of a signal_type (v0.4.19).",
        axis="defense_flag",
    )
    for key, name, desc in DEFENSE_FLAGS:
        defense_root.children.append(CodeNode(
            guid=_stable_guid(f"defense:{key}"),
            name=name,
            description=desc,
            axis="defense_flag",
        ))

    # ---- Quality flag siblings ----
    quality_root = CodeNode(
        guid=_stable_guid("quality_flags_root"),
        name="Quality flags",
        description="Gold-set protocol flags — keep/drop + actor-attribution check.",
        axis="quality_flag",
    )
    for key, name, desc in QUALITY_FLAGS:
        quality_root.children.append(CodeNode(
            guid=_stable_guid(f"quality:{key}"),
            name=name,
            description=desc,
            axis="quality_flag",
        ))

    codes = list(signal_type_nodes.values()) + [defense_root, quality_root]
    book = CodeBook(codes=codes)
    # Build flat name lookup.
    for node in book.all_nodes():
        book.by_name[node.name] = node
    return book


# ---------- importer reverse maps ----------


def signal_type_from_display(name: str) -> str | None:
    """Reverse SIGNAL_TYPE_DISPLAY."""
    for key, display in SIGNAL_TYPE_DISPLAY.items():
        if display == name:
            return key
    return None


def defense_flag_from_display(name: str) -> str | None:
    for key, display, _ in DEFENSE_FLAGS:
        if display == name:
            return key
    return None


def quality_flag_from_display(name: str) -> str | None:
    """Returns the gold-set field this quality flag maps to.

    'Keep — worth keeping'   → 'gold_keep_true'
    'Drop — should have …'   → 'gold_keep_false'
    'Actor attribution …'    → 'gold_actor_correct' | 'gold_actor_wrong'
    """
    for key, display, _ in QUALITY_FLAGS:
        if display == name:
            return key
    return None
