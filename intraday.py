"""
intraday.py — Intraday watchlist scanner
=========================================
Loads watchlist.json, fetches today's data,
alerts if close > level. Projects morning session volume.

Usage:
    python intraday.py             # print only
    python intraday.py --discord   # send to Discord
"""

import os, sys, json, time, argparse
from datetime import datetime
import pytz
import requests
import yfinance as yf
import pandas as pd

ROOT    = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from config import CFG
from app.core.paper_trade import close_positions, open_positions, check_positions, load_state
from output.report import print_intraday
from output.notifications import send_intraday_alert, send_paper_trade_update, send_review_alert

BKK     = pytz.timezone('Asia/Bangkok')
WL_PATH = os.path.join(ROOT, 'data', 'watchlist.json')
STATE_PATH = os.path.join(ROOT, 'data', 'alert_state.json')

parser = argparse.ArgumentParser()
parser.add_argument('--discord', action='store_true')
parser.add_argument('--review', action='store_true')
args = parser.parse_args()


def _alert_key(ticker, level, kind=None):
    kind_part = str(kind or '').lower()
    return f'{ticker}|{kind_part}|{float(level):.4f}'


def _load_alert_state(date_str):
    state = {'date': date_str, 'alerted': [], 'failed': []}
    if not os.path.exists(STATE_PATH):
        return state

    try:
        with open(STATE_PATH) as f:
            saved = json.load(f)
    except Exception:
        return state

    if saved.get('date') != date_str:
        return state

    normalized = []
    for item in saved.get('alerted', []):
        if isinstance(item, dict):
            ticker = item.get('ticker')
            level = item.get('level')
            if ticker and level is not None:
                normalized.append(dict(
                    ticker=ticker,
                    level=float(level),
                    kind=item.get('kind', ''),
                    key=item.get('key') or _alert_key(ticker, level, item.get('kind')),
                    alerted_at=item.get('alerted_at'),
                ))
        elif isinstance(item, str):
            normalized.append(dict(ticker=item, level=None, kind='', key=item, alerted_at=None))

    failed = []
    for item in saved.get('failed', []):
        if isinstance(item, dict):
            ticker = item.get('ticker')
            level = item.get('level')
            if ticker and level is not None:
                failed.append(dict(
                    ticker=ticker,
                    level=float(level),
                    kind=item.get('kind', ''),
                    key=item.get('key') or _alert_key(ticker, level, item.get('kind')),
                    failed_at=item.get('failed_at'),
                    close=item.get('close'),
                ))

    state['alerted'] = normalized
    state['failed'] = failed
    return state


def _save_alert_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def proj_volume(cur_volume, avg_volume, now):
    """Project full trading day RVol based on time elapsed.
    SET hours: 10:00-12:30 (150min) + 14:00-16:30 (150min) = 300min total.
    """
    if avg_volume <= 0:
        return 0.0
    open_min   = 10 * 60          # 10:00
    lunch_s    = 12 * 60 + 30     # 12:30
    lunch_e    = 14 * 60          # 14:00
    close_min  = 16 * 60 + 30     # 16:30
    total_min  = 300              # 150 + 150

    now_min = now.hour * 60 + now.minute

    if now_min <= lunch_s:
        # Morning session — elapsed since open
        elapsed = max(now_min - open_min, 1)
    elif now_min < lunch_e:
        # Lunch break — morning complete = 150min
        elapsed = 150
    else:
        # Afternoon session — add 150min morning + elapsed since 14:00
        elapsed = 150 + max(now_min - lunch_e, 1)

    elapsed   = min(elapsed, total_min)
    proj_vol  = cur_volume * total_min / elapsed
    return round(proj_vol / avg_volume, 2)


def fetch_today(ticker):
    try:
        df = yf.download(ticker, period='5d', interval='1d',
                         auto_adjust=True, progress=False)
        if df is None or len(df) == 0:
            return None
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        last = df.iloc[-1]
        return dict(close=float(last['Close']), volume=float(last['Volume']))
    except Exception as e:
        print(f'({e})', end=' ')
        return None


def fetch_price_and_ema10(tickers: list) -> tuple[dict, dict]:
    """Fetch current close + EMA10 for open position tickers (needs 30d history)."""
    prices = {}
    ema10s = {}
    if not tickers:
        return prices, ema10s
    try:
        raw = yf.download(tickers, period='30d', interval='1d',
                          auto_adjust=True, progress=False,
                          group_by='ticker' if len(tickers) > 1 else None)
        for ticker in tickers:
            try:
                df = raw[ticker] if len(tickers) > 1 else raw
                if df is None or len(df) < 2:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                prices[ticker] = float(df['Close'].iloc[-1])
                ema10s[ticker] = float(df['Close'].ewm(span=10, adjust=False).mean().iloc[-1])
            except Exception:
                continue
    except Exception as e:
        print(f'  Position price fetch error: {e}')
    return prices, ema10s


def criteria_label(rsm, rvol, stretch=0):
    rvol_ok = rvol >= CFG.get('rvol_min', 1.5)
    rsm_ok  = rsm  >= CFG.get('rs_momentum_min', 70)
    if stretch > 4: return 'STR'
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def run():
    now = datetime.now(BKK)
    date_str = now.strftime('%Y-%m-%d')

    alert_state = _load_alert_state(date_str)
    alerted_keys = {item.get('key') for item in alert_state['alerted']}
    legacy_tickers = {item.get('ticker') for item in alert_state['alerted'] if item.get('level') is None}
    failed_keys = {item.get('key') for item in alert_state.get('failed', [])}

    if not os.path.exists(WL_PATH):
        print('  watchlist.json not found — run main.py first.')
        return

    with open(WL_PATH) as f:
        watchlist = json.load(f)

    if not watchlist:
        print('  Watchlist is empty.')
        return

    try:
        from app.core.settrade_client import get_market_data
        get_market_data()
        data_source = "SETTRADE OpenAPI"
    except Exception:
        data_source = "Yahoo Finance (Fallback)"

    tickers = list({w['ticker'] for w in watchlist})
    print(f'\n  [{now.strftime("%H:%M")}] Checking {len(tickers)} stocks... (Data Source: {data_source})')

    # Batch download data
    print(f'  Downloading data...', flush=True)
    data = {}
    use_yfinance = False
    
    try:
        from app.core.settrade_client import get_market_data
        market = get_market_data()
        for ticker in tickers:
            symbol = ticker.replace('.BK', '')
            try:
                quote = market.get_quote_symbol(symbol)
                last_price = quote.get('last') or quote.get('close') or quote.get('result', {}).get('last')
                vol = quote.get('totalVolume') or quote.get('volume') or quote.get('result', {}).get('totalVolume')
                if last_price:
                    data[ticker] = dict(close=float(last_price), volume=float(vol))
            except Exception:
                continue
        if not data:
            # If settrade connected but returned empty for all
            raise ValueError("No data returned from Settrade")
    except Exception as e:
        print(f'  [fallback] Settrade failed for intraday ({e}). Using yfinance.', flush=True)
        use_yfinance = True
        
    if use_yfinance:
        try:
            raw = yf.download(tickers, period='5d', interval='1d',
                              auto_adjust=True, progress=False, group_by='ticker')
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        df = raw
                    else:
                        df = raw[ticker]
                    if df is None or len(df) == 0:
                        continue
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0] for c in df.columns]
                    last = df.iloc[-1]
                    data[ticker] = dict(close=float(last['Close']), volume=float(last['Volume']))
                except Exception:
                    continue
        except Exception as e:
            print(f'  Download error: {e}')
            return

    for ticker in tickers:
        short   = ticker.replace('.BK', '')
        levels  = [w['level'] for w in watchlist if w['ticker'] == ticker]
        lvl_str = ', '.join(f'฿{l:.2f}' for l in levels)
        d       = data.get(ticker)
        if d:
            print(f'  {short:<8}  levels {lvl_str:<20}  close ฿{d["close"]:.2f}')
        else:
            print(f'  {short:<8}  levels {lvl_str:<20}  no data')

    # ── Check open paper positions for TP/SL/EMA10 exit ─────────────────
    open_pos_tickers = list({
        p['ticker_full'] for p in load_state(CFG).get('positions', [])
        if p.get('status') == 'OPEN'
    })
    extra_tickers = [t for t in open_pos_tickers if t not in data]
    pos_prices, pos_ema10s = fetch_price_and_ema10(open_pos_tickers)
    # merge watchlist prices into pos_prices (already fetched)
    for t, d in data.items():
        if t not in pos_prices:
            pos_prices[t] = d['close']
    position_exit_events = check_positions(pos_prices, pos_ema10s, CFG, now)
    if position_exit_events:
        print(f'  {len(position_exit_events)} position exit(s) triggered.')
        if args.discord:
            send_paper_trade_update(position_exit_events, now, title='PAPER TRADE EXIT')

    signals = []
    seen    = set()
    for w in watchlist:
        ticker = w['ticker']
        level  = w['level']
        d      = data.get(ticker)
        if not d:
            continue
            
        key = (ticker, level)
        if key in seen:
            continue
        seen.add(key)

        if args.review:
            key_id = _alert_key(ticker, level, w.get('kind'))
            was_alerted = key_id in alerted_keys or ticker in legacy_tickers
            if was_alerted and d['close'] < level:
                avg_vol  = w.get('avg_volume', 0)
                cur_rvol = round(d['volume'] / avg_vol, 2) if avg_vol > 0 else 0
                proj_rv  = proj_volume(d['volume'], avg_vol, now)
                rsm      = w.get('rsm', 0)
                stretch  = w.get('stretch', 0)
                crit     = criteria_label(rsm, proj_rv, stretch)
                signals.append(dict(
                    ticker    = ticker.replace('.BK', ''),
                    ticker_full = ticker,
                    level     = level,
                    close     = d['close'],
                    cur_rvol  = cur_rvol,
                    kind      = 'Hz' if w.get('kind') == 'hz' else 'TL',
                    rsm       = rsm,
                    stretch   = stretch,
                    criteria  = crit,
                    atr       = w.get('atr', 0),
                    tl_angle  = w.get('tl_angle')
                ))
                if key_id not in failed_keys:
                    alert_state.setdefault('failed', []).append(dict(
                        ticker=ticker,
                        level=float(level),
                        kind=w.get('kind', ''),
                        key=key_id,
                        failed_at=now.isoformat(timespec='seconds'),
                        close=round(float(d['close']), 4),
                    ))
                    failed_keys.add(key_id)
            continue

        if d['close'] <= level:
            continue

        avg_vol  = w.get('avg_volume', 0)
        cur_rvol = round(d['volume'] / avg_vol, 2) if avg_vol > 0 else 0
        proj_rv  = proj_volume(d['volume'], avg_vol, now)
        crit     = criteria_label(w.get('rsm', 0), proj_rv, w.get('stretch', 0))

        if crit not in ('Prime', 'RVOL'):
            continue

        key_id = _alert_key(ticker, level, w.get('kind'))
        if key_id in alerted_keys:
            continue

        alert_state['alerted'].append(dict(
            ticker=ticker,
            level=float(level),
            kind=w.get('kind', ''),
            key=key_id,
            alerted_at=now.isoformat(timespec='seconds'),
        ))
        alerted_keys.add(key_id)

        signals.append(dict(
            ticker    = ticker.replace('.BK', ''),
            ticker_full = ticker,
            level     = level,
            close     = d['close'],
            cur_rvol  = cur_rvol,
            proj_rvol = proj_rv,
            kind      = 'Hz' if w.get('kind') == 'hz' else 'TL',
            rsm       = w.get('rsm', 0),
            stretch   = w.get('stretch', 0),
            atr       = w.get('atr', 0),
            criteria  = crit,
            tl_angle  = w.get('tl_angle'),
        ))

    if args.review:
        if not signals:
            print('  No false breakouts detected.')
            return
        print(f"  {len(signals)} false breakouts detected.")
        closed_events = close_positions(signals, now, CFG, reason='FALSE_BREAKOUT')
        _save_alert_state(alert_state)
        if args.discord:
            send_review_alert(signals, now, CFG)
            if closed_events:
                send_paper_trade_update(closed_events, now, title='PAPER TRADE EXIT')
        return

    if not signals:
        print('  No breakouts detected.')
        return

    # Save state to prevent duplicate alerts
    _save_alert_state(alert_state)

    print_intraday(signals, now.strftime('%Y-%m-%d'), now.strftime('%H:%M'))

    alert = signals
    prime_only = [s for s in alert if s.get('criteria') == 'Prime']
    opened_events = open_positions(prime_only, now, CFG) if prime_only else []

    if args.discord:
        if alert:
            send_intraday_alert(alert, now, CFG)
            if opened_events:
                send_paper_trade_update(opened_events, now, title='PAPER TRADE ENTRY')
        else:
            print('  No alertable signals — notifications skipped')


if __name__ == '__main__':
    run()
