"""Supabase persistence — writes to the same tables as System A.

The Hermes system tags every row with `system='hermes'` so the thesis can
distinguish output by system in cross-system comparisons.
"""

from .supabase_client import SupabaseStore, SignalRow

__all__ = ["SupabaseStore", "SignalRow"]
