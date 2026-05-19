"""Telegram gateway — stub.

The architecture diagram marks Telegram as "optional". To wire it up later:

1. `pip install python-telegram-bot`
2. Register a bot via @BotFather and put the token in `TELEGRAM_BOT_TOKEN`
3. Replace the stub below with a real bot that maps `/run` to
   `runner.cmd_run_once` and `/status` to a recent-runs query.

For now this file exists so the import path matches the architecture diagram.
"""

from __future__ import annotations


class TelegramGatewayStub:
    enabled = False

    @classmethod
    def maybe_serve(cls) -> None:
        # Intentionally a no-op. The cron-driven runner is the live entry point.
        return None
