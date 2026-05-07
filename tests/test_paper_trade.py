from __future__ import annotations

from app.core.paper_trade import _partial_lot, _position_shares


CFG = {
    'capital': 100_000,
    'commission': 0.0015,
    'risk_pct': 0.005,
    'sl_mult': 1,
}


def test_position_shares_skips_when_risk_size_below_board_lot():
    # Risk budget 500 / ATR 10 = 50 shares, below SET 100-share board lot.
    assert _position_shares(entry_price=300, atr=10, cash=100_000, cfg=CFG) == 0


def test_position_shares_caps_to_cash_without_exceeding_risk_size():
    # Risk size is 500 shares, but cash can afford only 300 shares.
    assert _position_shares(entry_price=100, atr=1, cash=35_000, cfg=CFG) == 300


def test_partial_lot_does_not_turn_small_tp_into_full_exit():
    assert _partial_lot(100, 0.30) == 0
    assert _partial_lot(300, 0.30) == 0
    assert _partial_lot(400, 0.30) == 100
