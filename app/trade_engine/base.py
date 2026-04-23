"""
app/trade_engine/base.py — Abstract TradeEngine interface
=========================================================
Both PaperTradeEngine and LiveTradeEngine implement this contract.
Switching between paper and live is a single env-var change:
  TRADE_MODE=paper   (default)
  TRADE_MODE=live
"""

from abc import ABC, abstractmethod
from datetime import datetime


class TradeEngine(ABC):

    @abstractmethod
    def open_positions(self, signals: list, now: datetime, cfg: dict) -> list:
        """
        Process a list of signal dicts, open new positions where eligible.
        Returns list of event dicts for each opened position.
        """

    @abstractmethod
    def close_positions(self, now: datetime, cfg: dict) -> list:
        """
        Evaluate all open positions against current prices.
        Close positions that hit SL/TP/trail criteria.
        Returns list of event dicts for each closed position.
        """

    @abstractmethod
    def check_positions(self, now: datetime, cfg: dict) -> dict:
        """
        Run the full intraday position-check cycle:
        - check for TP1/TP2/SL/trail hits
        - detect fakeouts
        Returns dict with keys: opened, closed, fakeouts.
        """

    @abstractmethod
    def get_state(self, cfg: dict) -> dict:
        """Return raw portfolio state dict (positions, cash, P&L, etc.)."""


def get_engine() -> TradeEngine:
    """Factory — returns the correct engine based on TRADE_MODE env var."""
    from app.config import TRADE_MODE
    if TRADE_MODE == 'live':
        from app.trade_engine.live import LiveTradeEngine
        return LiveTradeEngine()
    from app.trade_engine.paper import PaperTradeEngine
    return PaperTradeEngine()
