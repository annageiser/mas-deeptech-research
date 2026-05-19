"""Tools Registry — pure-Python callables the AIAgent can request via JSON."""

from .registry import ToolsRegistry, ToolDef, register_default_tools

__all__ = ["ToolsRegistry", "ToolDef", "register_default_tools"]
