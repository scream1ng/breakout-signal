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
from output.report import print_intraday
from output.notifications import send_intraday_alert

BKK     = pytz.timezone('Asia/Bangkok')
WL_PATH = os.path.join(ROOT, 'watchlist.json')

parser = argparse.ArgumentParser()
parser.add_argument('--discord', action='store_true')
args = parser.parse_args()


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


def criteria_label(rsm, rvol, stretch=0):
    rvol_ok = rvol >= CFG.get('rvol_min', 1.5)
    rsm_ok  = rsm  >= CFG.get('rs_momentum_min', 70)
    if (rvol_ok or rsm_ok) and stretch > 4: return 'STR'
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def run():
    now = datetime.now(BKK)

    if not os.path.exists(WL_PATH):
        print('  watchlist.json not found — run main.py first.')
        return

    with open(WL_PATH) as f:
        watchlist = json.load(f)

    if not watchlist:
        print('  Watchlist is empty.')
        return

    try:
        from core.settrade_client import get_market_data
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
        from core.settrade_client import get_market_data
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

    signals = []
    seen    = set()
    for w in watchlist:
        ticker = w['ticker']
        level  = w['level']
        d      = data.get(ticker)
        if not d or d['close'] <= level:
            continue
        key = (ticker, level)
        if key in seen:
            continue
        seen.add(key)

        avg_vol  = w.get('avg_volume', 0)
        cur_rvol = round(d['volume'] / avg_vol, 2) if avg_vol > 0 else 0
        proj_rv  = proj_volume(d['volume'], avg_vol, now)
        crit     = criteria_label(w.get('rsm', 0), cur_rvol, w.get('stretch', 0))

        signals.append(dict(
            ticker    = ticker.replace('.BK', ''),
            level     = level,
            close     = d['close'],
            cur_rvol  = cur_rvol,
            proj_rvol = proj_rv,
            kind      = 'Hz' if w.get('kind') == 'hz' else 'TL',
            rsm       = w.get('rsm', 0),
            stretch   = w.get('stretch', 0),
            criteria  = crit,
        ))

    if not signals:
        print('  No breakouts detected.')
        return

    print_intraday(signals, now.strftime('%Y-%m-%d'), now.strftime('%H:%M'))

    if args.discord:
        alert = [s for s in signals if s['criteria'] in ('Prime', 'RVOL', 'RSM', 'STR')]
        if alert:
            send_intraday_alert(alert, now, CFG)
        else:
            print('  No alertable signals — Discord skipped')


if __name__ == '__main__':
    run()