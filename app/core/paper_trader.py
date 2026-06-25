"""
app/core/paper_trader.py — Live paper trading for Prime breakout signals.

Storage: DailyState key 'paper_trades' (DB) or data/paper_trades.json (fallback).
Position sizing: capital × risk_pct / (ATR × sl_atr_mult), rounded DOWN to 100-lot.
Exits: TP1 (partial ~30%), TP2 (partial ~30%), Breakeven SL, EMA10 trail, SL, Fakeout.
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

def _calc_shares(atr, cfg):
    """Shares to buy, rounded DOWN to nearest 100-lot. Returns 0 if < 1 lot."""
    sl_distance = atr * cfg.get('sl_atr_mult', 1)
    if sl_distance <= 0:
        return 0
    risk_amount = cfg['capital'] * cfg.get('risk_pct', 0.005)
    return int(risk_amount / sl_distance // 100) * 100


def _partial_lots(shares_held):
    """Shares to sell at TP1/TP2 (30%, rounded down to 100-lot; min 1 lot if shares_held≥200)."""
    target = int(shares_held * 0.30 // 100) * 100
    if target == 0 and shares_held >= 200:
        return 100
    return target


# ── Open position ─────────────────────────────────────────────────────────────

def open_position(signal, cfg, now, open_positions):
    """
    Create a paper trade for a Prime breakout signal.
    Returns (trade_dict, None) on success or (None, error_str) on skip.
    signal keys: ticker_full, close, atr, rsm, level, kind, criteria
    """
    ticker = signal.get('ticker_full') or signal.get('ticker', '')
    entry_price = float(signal.get('close') or 0)
    atr = float(signal.get('atr') or 0)

    if not entry_price or atr <= 0:
        return None, f'{ticker}: missing price or ATR'

    if any(p['ticker'] == ticker for p in open_positions):
        return None, f'{ticker}: already open'

    shares = _calc_shares(atr, cfg)
    if shares < 100:
        budget = cfg['capital'] * cfg.get('risk_pct', 0.005)
        return None, f'{ticker}: ATR={atr:.2f} too large for 1 lot (budget ฿{budget:.0f})'

    deployed = sum(p['entry_price'] * p['shares_remaining'] for p in open_positions)
    available = cfg['capital'] - deployed
    cost = entry_price * shares
    if cost > available:
        return None, f'{ticker}: need ฿{cost:,.0f}, only ฿{available:,.0f} available'

    commission = cfg.get('commission', 0.0015)
    sl_d = atr * cfg.get('sl_atr_mult', 1)

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
        'tp1':              round(entry_price + cfg.get('tp1_atr_mult', 2) * sl_d, 4),
        'tp2':              round(entry_price + cfg.get('tp2_atr_mult', 4) * sl_d, 4),
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

def fetch_exit_data(open_positions):
    """
    Download 30d daily OHLCV for open position tickers.
    Returns {ticker: {close, ema10, bars_since_entry}}.
    """
    if not open_positions:
        return {}

    entry_map = {p['ticker']: p['entry_date'] for p in open_positions}
    tickers = list(entry_map.keys())
    result = {}

    try:
        raw = yf.download(
            tickers, period='30d', interval='1d',
            auto_adjust=True, progress=False,
            group_by='ticker' if len(tickers) > 1 else None,
        )
        for ticker in tickers:
            try:
                df = raw[ticker] if len(tickers) > 1 else raw
                if df is None or len(df) < 2:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                close_s = df['Close'].dropna()
                if len(close_s) < 2:
                    continue
                ema10 = float(close_s.ewm(span=10, adjust=False).mean().iloc[-1])
                entry_date = entry_map[ticker]
                bars = sum(1 for d in close_s.index if str(d)[:10] > entry_date)
                result[ticker] = {
                    'close':            round(float(close_s.iloc[-1]), 4),
                    'ema10':            round(ema10, 4),
                    'bars_since_entry': bars,
                }
            except Exception as e:
                logger.debug('fetch_exit_data %s: %s', ticker, e)
    except Exception as e:
        logger.warning('fetch_exit_data: %s', e)

    return result


# ── Check exits ───────────────────────────────────────────────────────────────

def check_exits(open_positions, exit_data, now, cfg):
    """
    Apply TP1/TP2/BE/SL/EMA10 exit rules to all open positions.
    Returns (still_open, newly_closed).
    """
    commission = cfg.get('commission', 0.0015)
    be_days = cfg.get('be_after_days', 3)

    still_open, newly_closed = [], []

    for pos in open_positions:
        pos = dict(pos)
        ed = exit_data.get(pos['ticker'])

        if not ed:
            still_open.append(pos)
            continue

        close = ed['close']
        ema10 = ed['ema10']
        bars = ed['bars_since_entry']
        pos['current_close'] = round(close, 4)
        pos['bars_held'] = bars

        # Breakeven
        if not pos['be_activated'] and bars >= be_days:
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
        ema_exit = close < ema10

        if sl_hit or ema_exit:
            at_be = abs(pos['sl'] - pos['entry_price']) < 0.001
            reason = 'EMA10' if ema_exit else ('BE' if at_be else 'SL')
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


def fakeout_exits(open_positions, fakeout_tickers, prices, now, cfg):
    """
    Exit positions whose tickers are in fakeout_tickers (close < level at 16:25 review).
    prices: {ticker: {'close': float}}
    Returns (still_open, newly_closed).
    """
    commission = cfg.get('commission', 0.0015)
    fakeout_set = set(fakeout_tickers)
    still_open, newly_closed = [], []

    for pos in open_positions:
        pos = dict(pos)
        if pos['ticker'] not in fakeout_set:
            still_open.append(pos)
            continue

        close = prices.get(pos['ticker'], {}).get('close', pos['entry_price'])
        exit_pnl = pos['realized_pnl']
        if pos['shares_remaining'] > 0:
            proceeds = close * pos['shares_remaining'] * (1 - commission)
            exit_pnl = round(exit_pnl + proceeds - pos['entry_price'] * pos['shares_remaining'], 2)

        pos.update(
            status='closed',
            exit_price=round(float(close), 4),
            exit_reason='Fakeout',
            exit_date=now.strftime('%Y-%m-%d'),
            shares_remaining=0,
            total_pnl=exit_pnl,
            pnl_pct=round(exit_pnl / (pos['entry_price'] * pos['shares']) * 100, 2) if pos['shares'] else 0,
            realized_pnl=exit_pnl,
            updated_at=now.isoformat(timespec='seconds'),
        )
        logger.info('[paper] %s FAKEOUT @ %.2f pnl=%.2f', pos['ticker'], close, exit_pnl)
        newly_closed.append(pos)

    return still_open, newly_closed


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
