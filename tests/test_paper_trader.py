from datetime import datetime

from app.core import paper_trader as pt

CFG = dict(
    capital=100_000, commission=0.0015, tp1_atr_mult=2, tp2_atr_mult=4,
    paper_risk_pct=0.0025, paper_sl_atr_mult=2, paper_trail='SMA50', paper_be_after_days=None,
)
NOW = datetime(2026, 11, 16, 10, 30)


def _sig(ticker='AAA.BK', close=10.0, atr=0.25):
    return dict(ticker_full=ticker, close=close, atr=atr, rsm=85, level=9.9, kind='Hz', criteria='Prime')


def test_sizing_uses_half_risk_and_two_atr_stop():
    trade, err = pt.open_position(_sig(), CFG, NOW, [])
    assert err is None
    # risk ฿250 / (2 × 0.25) = 500 shares
    assert trade['shares'] == 500
    assert trade['sl'] == 9.5
    assert trade['tp1'] == 10.5 and trade['tp2'] == 11.0   # +2 / +4 ATR


def test_available_cash_counts_realized_losses():
    deployed = [dict(ticker='X.BK', entry_price=100.0, shares_remaining=900)]   # ฿90,000 invested
    trade, err = pt.open_position(_sig(close=10.0), CFG, NOW, deployed, realized_pnl=0)
    assert trade is not None                                     # ฿5,000 cost fits in ฿10,000
    trade, err = pt.open_position(_sig(close=10.0), CFG, NOW, deployed, realized_pnl=-6_000)
    assert trade is None and 'available' in err                  # only ฿4,000 left after losses


def _open(**kw):
    trade, _ = pt.open_position(_sig(), CFG, datetime(2026, 11, 10), [])
    trade.update(kw)
    return trade


def test_no_breakeven_and_trail_exit_on_sma50():
    pos = _open()
    ed = {'AAA.BK': dict(close=9.8, trail=9.6, bars_since_entry=5)}
    still, closed = pt.check_exits([pos], ed, NOW, CFG)
    assert closed == [] and still[0]['sl'] == 9.5 and not still[0]['be_activated']

    ed = {'AAA.BK': dict(close=9.7, trail=9.75, bars_since_entry=6)}
    still, closed = pt.check_exits([pos], ed, NOW, CFG)
    assert still == [] and closed[0]['exit_reason'] == 'SMA50'


def test_stop_loss_exit():
    ed = {'AAA.BK': dict(close=9.45, trail=9.0, bars_since_entry=1)}
    still, closed = pt.check_exits([_open()], ed, NOW, CFG)
    assert closed[0]['exit_reason'] == 'SL'


def test_tp1_partial_keeps_position_open():
    ed = {'AAA.BK': dict(close=10.6, trail=9.5, bars_since_entry=4)}
    still, closed = pt.check_exits([_open()], ed, NOW, CFG)
    assert closed == [] and still[0]['tp1_hit'] and still[0]['shares_remaining'] == 400


def _store():
    return pt._empty()


def test_buy_when_market_up_at_live_price():
    store = _store()
    trade, reason = pt.buy_decision(_sig(close=10.1), True, store, CFG, NOW)
    assert reason is None and trade['entry_price'] == 10.1
    assert store['open'][0]['ticker'] == 'AAA.BK'


def test_rsm_label_buys_without_volume():
    trade, _ = pt.buy_decision(dict(_sig(), criteria='RSM'), True, _store(), CFG, NOW)
    assert trade is not None


def test_watch_only_reasons():
    store = _store()
    assert pt.buy_decision(_sig(), False, store, CFG, NOW) == (None, 'market down')
    assert pt.buy_decision(dict(_sig(), criteria='STR'), True, store, CFG, NOW) == (None, 'overextended')
    assert pt.buy_decision(dict(_sig(), criteria='RVOL', rsm=70), True, store, CFG, NOW)[1].startswith('RSM 70')
    assert store['open'] == []


def test_no_double_buy_same_ticker():
    store = _store()
    pt.buy_decision(_sig(), True, store, CFG, NOW)
    trade, reason = pt.buy_decision(_sig(), True, store, CFG, NOW)
    assert trade is None and reason == 'already open'


def test_buy_respects_cash_after_losses():
    store = _store()
    store['open'] = [dict(ticker='X.BK', entry_price=100.0, shares_remaining=900)]
    store['closed'] = [dict(total_pnl=-6_000)]
    trade, reason = pt.buy_decision(_sig(), True, store, CFG, NOW)
    assert trade is None and 'available' in reason
