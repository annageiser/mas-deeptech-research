"""AIAgent — the single core loop.

Implements the Hermes pattern: a single LLM-driven loop that, given a target
(here: a Swiss-quantum actor), iterates {plan → tool call → observe → repeat}
until it calls `finish_actor` or the iteration cap fires.
"""

from .core_loop import AIAgent, AgentResult

__all__ = ["AIAgent", "AgentResult"]
