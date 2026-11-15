"""
app/core/paper_trader.py — Live paper trading for Prime breakout signals (v2 rules).

v2 rules (evidence: backtest_research.py, Nov 2026):
  Entry : the 15-min scan buys a breakout at the live price when RSM ≥ min,
          not overextended, and SET > its SMA50 (from the last EOD scan).
          Discord BUY alerts == paper buys. Fakeouts are held (stop handles them).
  Size  : capital × paper_risk_pct / (ATR × paper_sl_atr_mult), DOWN to 100-lot.
  Exits : checked once per day at the 16:25 review (≈ close), never on 15-min wobbles.
          SL at entry − paper_sl_atr_mult × ATR; TP1/TP2 partial (~30%) at +2/+4 ATR;
          remaining shares exit when close < paper_trail MA (SMA50).

Storage: DailyState key 'paper_trades' (DB) or data/paper_trades.json (fallback).
"""

import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_JSON_PATH = os.path.join(ROOT, 'data', 'paper_trades.json')
_STATE_KEY = 'paper_trades'


# ── Storage ───────────────────────────────────────────────────────────────────

def _empty():
    return {'open': [], 'closed': []}


def load_trades():
    """Load paper trade store. DB first, JSON fallback."""
    try:
        from app.storage.state import load_state
        saved = load_state(_STATE_KEY)
        if saved is not None:
            return saved
    except Exception:
        pass
    if os.path.exists(_JSON_PATH):
        try:
            with open(_JSON_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return _empty()


def save_trades(store):
    """Save paper trade store to DB and JSON fallback."""
    try:
        from app.storage.state import save_state
        save_state(_STATE_KEY, store)
    except Exception:
        pass
    os.makedirs(os.path.dirname(_JSON_PATH), exist_ok=True)
    with open(_JSON_PATH, 'w') as f:
        json.dump(store, f, indent=2)


# ── Position sizing ───────────────────────────────────────────────────────────

def _sl_mult(cfg):
    return cfg.get('paper_sl_atr_mult', cfg.get('sl_atr_mult', 1))


def _risk_pct(cfg):
    return cfg.get('paper_risk_pct', cfg.get('risk_pct', 0.005))


def _calc_shares(atr, cfg):
    """Shares to buy, rounded DOWN to nearest 100-lot. Returns 0 if < 1 lot."""
    sl_distance = atr * _sl_mult(cfg)
    if sl_distance <= 0:
        return 0
    risk_amount = cfg['capital'] * _risk_pct(cfg)
    return int(risk_amount / sl_distance // 100) * 100


def _partial_lots(shares_held):
    """Shares to sell at TP1/TP2 (30%, rounded down to 100-lot; min 1 lot if shares_held≥200)."""
    target = int(shares_held * 0.30 // 100) * 100
    if target == 0 and shares_held >= 200:
        return 100
    return target


# ── Open position ─────────────────────────────────────────────────────────────

def open_position(signal, cfg, now, open_positions, realized_pnl=0.0):
    """
    Create a paper trade for a Prime breakout signal.
    Returns (trade_dict, None) on success or (None, error_str) on skip.
    signal keys: ticker_full, close, atr, rsm, level, kind, criteria
    realized_pnl: P/L of closed trades — available cash = capital + realized − deployed.
    """
    ticker = signal.get('ticker_full') or signal.get('ticker', '')
    entry_price = float(signal.get('close') or 0)
    atr = float(signal.get('atr') or 0)

    if not entry_price or pd.isna(entry_price) or pd.isna(atr) or atr <= 0:
        return None, f'{ticker}: missing price or ATR'

    if any(p['ticker'] == ticker for p in open_positions):
        return None, f'{ticker}: already open'

    shares = _calc_shares(atr, cfg)
    if shares < 100:
        budget = cfg['capital'] * _risk_pct(cfg)
        return None, f'{ticker}: ATR={atr:.2f} too large for 1 lot (budget ฿{budget:.0f})'

    deployed = sum(p['entry_price'] * p['shares_remaining'] for p in open_positions)
    available = cfg['capital'] + realized_pnl - deployed
    cost = entry_price * shares
    if cost > available:
        return None, f'{ticker}: need ฿{cost:,.0f}, only ฿{available:,.0f} available'

    commission = cfg.get('commission', 0.0015)
    sl_d = atr * _sl_mult(cfg)

    trade = {
        'ticker':           ticker,
        'entry_date':       now.strftime('%Y-%m-%d'),
        'entry_time':       now.isoformat(timespec='seconds'),
        'entry_price':      round(entry_price, 4),
        'entry_level':      round(float(signal.get('level', 0)), 4),
        'shares':           shares,
        'shares_remaining': shares,
        'atr':              round(atr, 4),
        'rsm':              round(float(signal.get('rsm', 0)), 1),
        'criteria':         signal.get('criteria', 'Prime'),
        'kind':             signal.get('kind', 'Hz'),
        'sl':               round(entry_price - sl_d, 4),
        'sl_initial':       round(entry_price - sl_d, 4),
        'tp1':              round(entry_price + cfg.get('tp1_atr_mult', 2) * atr, 4),
        'tp2':              round(entry_price + cfg.get('tp2_atr_mult', 4) * atr, 4),
        'be_activated':     False,
        'tp1_hit':          False,
        'tp1_shares_sold':  0,
        'tp2_hit':          False,
        'tp2_shares_sold':  0,
        'realized_pnl':     round(-(entry_price * shares * commission), 2),
        'current_close':    round(entry_price, 4),
        'status':           'open',
        'exit_price':       None,
        'exit_reason':      None,
        'exit_date':        None,
        'total_pnl':        None,
        'pnl_pct':          None,
        'bars_held':        0,
        'updated_at':       now.isoformat(timespec='seconds'),
    }
    return trade, None


# ── Exit data fetch ───────────────────────────────────────────────────────────

def fetch_exit_data(open_positions, cfg=None):
    """
    Download ~6mo daily OHLCV for open position tickers.
    Returns {ticker: {close, trail, bars_since_entry}} — trail = paper_trail MA value.
    """
    if not open_positions:
        return {}

    trail_name = (cfg or {}).get('paper_trail', 'SMA50')
    entry_map = {p['ticker']: p['entry_date'] for p in open_positions}
    tickers = list(entry_map.keys())
    result = {}

    try:
        raw = yf.download(
            tickers, period='6mo', interval='1d',
            auto_adjust=True, progress=False, group_by='ticker',
        )
        for ticker in tickers:
            try:
                # group_by='ticker' gives (ticker, field) columns even for one ticker
                df = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
                if df is None or len(df) < 2:
                    continue
                close_s = df['Close'].dropna()
                if len(close_s) < 2:
                    continue
                trail = _ma(close_s, trail_name)
                if trail is None:
                    continue
                entry_date = entry_map[ticker]
                bars = sum(1 for d in close_s.index if str(d)[:10] > entry_date)
                result[ticker] = {
                    'close':            round(float(close_s.iloc[-1]), 4),
                    'trail':            round(trail, 4),
                    'bars_since_entry': bars,
                }
            except Exception as e:
                logger.debug('fetch_exit_data %s: %s', ticker, e)
    except Exception as e:
        logger.warning('fetch_exit_data: %s', e)

    return result


def _ma(close_s, name):
    """Last value of an MA named like 'SMA50' / 'EMA20'; None if not enough bars."""
    kind, n = name[:3].upper(), int(name[3:])
    if len(close_s) < n:
        return None
    if kind == 'EMA':
        return float(close_s.ewm(span=n, adjust=False).mean().iloc[-1])
    return float(close_s.rolling(n).mean().iloc[-1])


# ── Check exits ───────────────────────────────────────────────────────────────

def check_exits(open_positions, exit_data, now, cfg):
    """
    Apply TP1/TP2/SL/trail-MA exit rules (+ optional breakeven) to all open positions.
    Run once per day near the close. Returns (still_open, newly_closed).
    """
    commission = cfg.get('commission', 0.0015)
    be_days = cfg.get('paper_be_after_days')        # None → no breakeven move
    trail_name = cfg.get('paper_trail', 'SMA50')

    still_open, newly_closed = [], []

    for pos in open_positions:
        pos = dict(pos)
        ed = exit_data.get(pos['ticker'])

        if not ed:
            still_open.append(pos)
            continue

        close = ed['close']
        trail = ed['trail']
        bars = ed['bars_since_entry']
        pos['current_close'] = round(close, 4)
        pos['bars_held'] = bars

        # Breakeven (off in v2)
        if be_days and not pos['be_activated'] and bars >= be_days:
            pos['sl'] = pos['entry_price']
            pos['be_activated'] = True

        # TP1
        if not pos['tp1_hit'] and close >= pos['tp1']:
            sell = min(_partial_lots(pos['shares']), pos['shares_remaining'])
            if sell >= 100:
                proceeds = pos['tp1'] * sell * (1 - commission)
                pos['realized_pnl'] = round(
                    pos['realized_pnl'] + proceeds - pos['entry_price'] * sell, 2)
                pos['shares_remaining'] -= sell
                pos['tp1_hit'] = True
                pos['tp1_shares_sold'] = sell
                logger.info('[paper] %s TP1 sold %d @ %.2f', pos['ticker'], sell, pos['tp1'])

        # TP2
        if pos['tp1_hit'] and not pos['tp2_hit'] and close >= pos['tp2']:
            remaining_after_tp1 = pos['shares'] - pos['tp1_shares_sold']
            sell = min(_partial_lots(remaining_after_tp1), pos['shares_remaining'])
            if sell >= 100:
                proceeds = pos['tp2'] * sell * (1 - commission)
                pos['realized_pnl'] = round(
                    pos['realized_pnl'] + proceeds - pos['entry_price'] * sell, 2)
                pos['shares_remaining'] -= sell
                pos['tp2_hit'] = True
                pos['tp2_shares_sold'] = sell
                logger.info('[paper] %s TP2 sold %d @ %.2f', pos['ticker'], sell, pos['tp2'])

        # Full exits
        sl_hit = close <= pos['sl']
        trail_exit = close < trail

        if sl_hit or trail_exit:
            at_be = abs(pos['sl'] - pos['entry_price']) < 0.001
            reason = ('BE' if at_be else 'SL') if sl_hit else trail_name
            exit_pnl = pos['realized_pnl']
            if pos['shares_remaining'] > 0:
                proceeds = close * pos['shares_remaining'] * (1 - commission)
                exit_pnl = round(exit_pnl + proceeds - pos['entry_price'] * pos['shares_remaining'], 2)
            pos.update(
                status='closed',
                exit_price=round(close, 4),
                exit_reason=reason,
                exit_date=now.strftime('%Y-%m-%d'),
                shares_remaining=0,
                total_pnl=exit_pnl,
                pnl_pct=round(exit_pnl / (pos['entry_price'] * pos['shares']) * 100, 2) if pos['shares'] else 0,
                realized_pnl=exit_pnl,
                updated_at=now.isoformat(timespec='seconds'),
            )
            logger.info('[paper] %s EXIT %s @ %.2f pnl=%.2f', pos['ticker'], reason, close, exit_pnl)
            newly_closed.append(pos)
        else:
            pos['updated_at'] = now.isoformat(timespec='seconds')
            still_open.append(pos)

    return still_open, newly_closed


# ── Buy decision (15-min scan) + market state ────────────────────────────────

BUY_CRITERIA = ('Prime', 'RSM')   # RSM ≥ min and not overextended; volume not required
_MARKET_KEY = 'market_regime'


def save_market(state):
    """EOD: persist {'date','set_close','set_sma50','up'} for the next session's scans."""
    try:
        from app.storage.state import save_state
        save_state(_MARKET_KEY, state)
    except Exception:
        pass
    os.makedirs(os.path.dirname(_JSON_PATH), exist_ok=True)
    with open(os.path.join(ROOT, 'data', f'{_MARKET_KEY}.json'), 'w') as f:
        json.dump(state, f, indent=2)


def load_market():
    try:
        from app.storage.state import load_state
        saved = load_state(_MARKET_KEY)
        if saved is not None:
            return saved
    except Exception:
        pass
    path = os.path.join(ROOT, 'data', f'{_MARKET_KEY}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def buy_decision(signal, market_up, store, cfg, now):
    """
    Decide at scan time whether to buy a breakout at the current price.
    Returns (trade, None) when bought (trade appended to store['open']),
    or (None, reason) when it stays watch-only.
    """
    if signal.get('criteria') not in BUY_CRITERIA:
        return None, {'STR': 'overextended', 'RVOL': f"RSM {round(signal.get('rsm', 0))} < min"}.get(
            signal.get('criteria'), 'criteria')
    if not market_up:
        return None, 'market down'
    realized = sum(t.get('total_pnl') or 0 for t in store.get('closed', []))
    trade, err = open_position(signal, cfg, now, store['open'], realized_pnl=realized)
    if not trade:
        return None, err.split(': ', 1)[-1]
    store['open'].append(trade)
    return trade, None


def archive_and_reset(now, rules_label='v2'):
    """Save the current paper store under a dated archive key, then start fresh."""
    from app.storage.state import save_state
    store = load_trades()
    archive_key = f"paper_trades_archive_{now.strftime('%Y-%m-%d')}"
    save_state(archive_key, store)
    os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
    with open(os.path.join(ROOT, 'data', f'{archive_key}.json'), 'w') as f:
        json.dump(store, f, indent=2)
    fresh = dict(_empty(), started_at=now.strftime('%Y-%m-%d'), rules=rules_label)
    save_trades(fresh)
    return archive_key, store


# ── Portfolio summary ─────────────────────────────────────────────────────────

def portfolio_summary(open_positions, closed_trades, cfg):
    capital = cfg.get('capital', 100_000)
    deployed = sum(p['entry_price'] * p['shares_remaining'] for p in open_positions)
    unrealized = sum(
        (p.get('current_close', p['entry_price']) - p['entry_price']) * p['shares_remaining']
        + p.get('realized_pnl', 0)
        for p in open_positions
    )
    realized = sum(t.get('total_pnl', 0) or 0 for t in closed_trades)
    n_closed = len(closed_trades)
    n_wins = sum(1 for t in closed_trades if (t.get('total_pnl') or 0) > 0)
    cash = capital + realized - deployed
    equity = capital + realized + unrealized
    return {
        'capital':        capital,
        'deployed':       round(deployed, 2),
        'available':      round(cash, 2),
        'cash':           round(cash, 2),
        'equity':         round(equity, 2),
        'realized_pnl':   round(realized, 2),
        'realized_pct':   round(realized / capital * 100, 2) if capital else 0,
        'unrealized_pnl': round(unrealized, 2),
        'unrealized_pct': round(unrealized / capital * 100, 2) if capital else 0,
        'n_open':         len(open_positions),
        'n_closed':       n_closed,
        'win_rate':       round(n_wins / n_closed * 100, 1) if n_closed else 0,
    }


if __name__ == '__main__':
    import argparse
    import pytz
    ap = argparse.ArgumentParser(description='Paper trade maintenance')
    ap.add_argument('--reset', action='store_true', help='archive current paper trades and start fresh')
    a = ap.parse_args()
    if a.reset:
        key, old = archive_and_reset(datetime.now(pytz.timezone('Asia/Bangkok')))
        print(f"Archived {len(old.get('closed', []))} closed / {len(old.get('open', []))} open → {key}. Fresh store saved.")
