"""
app/trade_engine/live.py — LiveTradeEngine (stub)
==================================================
Will route orders through the SETTRADE Open API once paper trading is
stable and the sandbox has been validated.

Switch by setting TRADE_MODE=live in .env.
"""

from datetime import datetime

from app.trade_engine.base import TradeEngine


class LiveTradeEngine(TradeEngine):
    """SETTRADE live-order implementation — not yet active."""

    def __init__(self):
        # Import lazily so the settrade-v2 SDK is only needed when TRADE_MODE=live
        from core.settrade_client import get_market_data  # noqa: F401 — validate creds early

    def open_positions(self, signals: list, now: datetime, cfg: dict) -> list:
        raise NotImplementedError(
            'LiveTradeEngine.open_positions is not yet implemented. '
            'Set TRADE_MODE=paper to use paper trading.'
        )

    def close_positions(self, now: datetime, cfg: dict) -> list:
        raise NotImplementedError('LiveTradeEngine.close_positions is not yet implemented.')

    def check_positions(self, now: datetime, cfg: dict) -> dict:
        raise NotImplementedError('LiveTradeEngine.check_positions is not yet implemented.')

    def get_state(self, cfg: dict) -> dict:
        raise NotImplementedError('LiveTradeEngine.get_state is not yet implemented.')
