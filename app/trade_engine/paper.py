"""
app/trade_engine/paper.py — PaperTradeEngine
=============================================
Thin wrapper around core/paper_trade.py.
All paper-trade logic stays in the existing module — this class
provides the standard TradeEngine interface on top of it.
"""

from datetime import datetime

from app.trade_engine.base import TradeEngine
import app.core.paper_trade as _pt


class PaperTradeEngine(TradeEngine):

    def open_positions(self, signals: list, now: datetime, cfg: dict) -> list:
        return _pt.open_positions(signals, now, cfg)

    def close_positions(self, now: datetime, cfg: dict) -> list:
        return _pt.close_positions(now, cfg)

    def check_positions(self, now: datetime, cfg: dict) -> dict:
        return _pt.check_positions(now, cfg)

    def get_state(self, cfg: dict) -> dict:
        return _pt.load_state(cfg)
