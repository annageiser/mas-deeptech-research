"""System B — Hermes-pattern single-agent runner.

Component map (matches the architecture diagram in docs/architecture.md):

  entry_points/      -> Entry Points + Gateway (CLI + optional Telegram stub)
  agent/             -> AIAgent (Core Loop)
  tools_registry/    -> Tools Registry (callable Python tools)
  skills_loader/     -> Skills Loader (SKILL.md discovery + loading)
  memory/            -> Memory Manager (SQLite procedural memory)
  providers/         -> Providers (Model API — OpenRouter)
  persistence/       -> Supabase writer (same tables as System A; system='hermes')
"""

__version__ = "0.1.0"
