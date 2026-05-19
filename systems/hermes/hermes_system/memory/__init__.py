"""Memory Manager — SQLite-backed procedural memory.

Three layers, mirroring Hermes Agent's design:
  L1 — current_context     : current actor + run id (in-process, not persisted)
  L2 — preference_facts    : `key=value` notes the user supplied (rare)
  L3 — procedural_skills   : compact summaries of successful past runs per actor
"""

from .sqlite_manager import MemoryManager

__all__ = ["MemoryManager"]
