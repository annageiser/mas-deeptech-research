"""Entry Points + Gateway.

The CLI entry point is implemented in `runner.py`. The Telegram gateway from
the architecture diagram is marked "optional" — left as a stub so the wiring
exists when the thesis decides to enable it.
"""

from .telegram_gateway import TelegramGatewayStub

__all__ = ["TelegramGatewayStub"]
