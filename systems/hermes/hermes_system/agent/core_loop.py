"""AIAgent core loop.

The model is given:
- a system prompt describing the task + the loaded skills + the tool schemas
- a user message stating "process actor X"
- a recall of past procedures for this actor (procedural memory)

Each iteration the assistant must reply with a strict JSON object:

    {"action": "tool", "tool": "<name>", "args": {...}}
or
    {"action": "finish", "summary_md": "..."}

The loop runs the tool, appends the (truncated) result to the conversation,
and continues until `finish` or `max_iterations`.

This is intentionally a thinner alternative to function-calling so the
behaviour stays comparable across OpenRouter free models, several of which
don't support tools natively.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..memory import MemoryManager
from ..providers import OpenRouterProvider
from ..skills_loader import SkillsLoader
from ..tools_registry import ToolsRegistry, register_default_tools


SYSTEM_PROMPT_TMPL = """You are the AIAgent of System B (Hermes-pattern) in a Swiss-quantum
ecosystem-mapping pipeline. You have a single goal per turn: process one
actor and register every signal worth recording.

LOADED SKILLS:
{skills_block}

AVAILABLE TOOLS (call exactly one per turn):
{tools_block}

PROCEDURAL MEMORY for this actor (most recent first; may be empty):
{memory_block}

TASK FOR THIS RUN:
You will receive an actor as a JSON object in the user message. For each
piece of evidence you discover, call `register_signal` exactly once. When
you've recorded everything you can find with the resources available, call
`finish_actor` with a short markdown brief.

PROTOCOL — every assistant reply MUST be a single JSON object with the shape:
  {{"action": "tool", "tool": "<tool_name>", "args": {{...}}}}
or
  {{"action": "finish", "summary_md": "..."}}

No prose, no markdown fences, no commentary. JSON only.
"""

USER_PROMPT_TMPL = """Process this actor:
{actor_json}

Iteration budget remaining: {budget}
"""


@dataclass
class AgentResult:
    actor_slug: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    brief_md: str = ""
    iterations_used: int = 0
    stopped_reason: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0] if "```" in text.rsplit("\n", 1)[-1] else text[:-3]
        text = text.strip()
    match = _JSON_RE.search(text)
    return match.group(0) if match else text


def _truncate(value: Any, max_chars: int = 4_000) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, default=str)
    return raw if len(raw) <= max_chars else raw[:max_chars] + " …(truncated)"


class AIAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: OpenRouterProvider,
        skills_loader: SkillsLoader,
        memory: MemoryManager,
        skill_names: list[str] | None = None,
    ):
        self.settings = settings
        self.provider = provider
        self.memory = memory
        self.skills = (
            skills_loader.selected_for(skill_names) if skill_names else skills_loader.discover()
        )

    def run_actor(self, actor: dict[str, Any]) -> AgentResult:
        actor_slug = str(actor.get("slug", "unknown"))
        signals: list[dict[str, Any]] = []
        registry = ToolsRegistry()
        register_default_tools(registry, actor_slug=actor_slug, signal_buffer=signals)

        skills_block = "\n\n".join(s.to_prompt_block() for s in self.skills) or "(no skills loaded)"
        tools_block = registry.schema_block()
        memory_block = self._render_memory(actor_slug)

        system_prompt = SYSTEM_PROMPT_TMPL.format(
            skills_block=skills_block,
            tools_block=tools_block,
            memory_block=memory_block,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        result = AgentResult(actor_slug=actor_slug)

        budget = self.settings.max_iterations_per_actor
        for i in range(budget):
            result.iterations_used = i + 1
            if i == 0:
                user = USER_PROMPT_TMPL.format(actor_json=json.dumps(actor), budget=budget - i)
                messages.append({"role": "user", "content": user})

            reply = self.provider.chat(messages=messages, max_tokens=1024, temperature=0.2)
            result.transcript.append({"role": "assistant", "content": reply})
            messages.append({"role": "assistant", "content": reply})

            try:
                step = json.loads(_strip_json(reply))
            except json.JSONDecodeError:
                messages.append(
                    {
                        "role": "user",
                        "content": "Your last reply was not valid JSON. Reply with a single JSON object now.",
                    }
                )
                continue

            action = step.get("action")
            if action == "finish":
                result.brief_md = step.get("summary_md", "")
                result.stopped_reason = "finish"
                break
            if action == "tool":
                tool = step.get("tool", "")
                args = step.get("args", {}) or {}
                try:
                    output = registry.call(tool, args)
                except Exception as exc:
                    output = f"ERROR: {type(exc).__name__}: {exc}"
                follow_up = f"Tool `{tool}` returned:\n{_truncate(output)}\n\nIterations remaining: {budget - (i + 1)}. Continue."
                messages.append({"role": "user", "content": follow_up})
                continue

            messages.append(
                {
                    "role": "user",
                    "content": "Unrecognised action. Reply with action='tool' or action='finish'.",
                }
            )
        else:
            result.stopped_reason = "max_iterations"

        result.signals = signals
        if result.brief_md:
            self.memory.record_procedure(
                actor_slug=actor_slug,
                summary=(result.brief_md or "")[:1500],
                successful_sources=sorted({s.get("source_kind", "") for s in signals if s.get("source_kind")}),
                common_signal_dimensions=sorted({s.get("dimension", "") for s in signals if s.get("dimension")}),
            )
        return result

    def _render_memory(self, actor_slug: str) -> str:
        past = self.memory.recall_procedure(actor_slug, limit=3)
        if not past:
            return "(none — this is the first time processing this actor)"
        lines = []
        for i, item in enumerate(past, 1):
            sources = ", ".join(item.get("successful_sources", []) or []) or "—"
            dims = ", ".join(item.get("common_signal_dimensions", []) or []) or "—"
            lines.append(f"{i}. ({item['created_at']}) sources={sources}; dims={dims}; summary: {item['summary'][:400]}")
        return "\n".join(lines)
