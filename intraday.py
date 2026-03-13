"""
scripts/intraday.py — Intraday watchlist scanner
=================================================
Loads watchlist.json (built by main.py EOD scan), downloads 1mo data
for each stock, checks if price broke above a pending level, and
projects RVol to predict if Prime criteria will be met by end of day.

Sends Discord alert only when a breakout is detected.

Usage:
    python scripts/intraday.py               # run once
    python scripts/intraday.py --loop        # run every 30min during market hours
    python scripts/intraday.py --discord     # send to Discord (default: print only)

Run from project root:
    cd swing_trader
    python scripts/intraday.py --discord --loop
"""

import os, sys, json, time, argparse
from datetime import datetime, date
import pytz

# ── Allow imports from project root ──────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import yfinance as yf
import pandas as pd
import numpy as np

import requests

from config import CFG

# ── Pure-python .env loader (no python-dotenv dependency) ────────────────────
def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip(); val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

# ── Constants ────────────────────────────────────────────────────────────────
BKK           = pytz.timezone('Asia/Bangkok')
MARKET_OPEN   = (10, 0)
MARKET_CLOSE  = (16, 30)
LOOP_INTERVAL = 30 * 60   # seconds
WL_PATH       = os.path.join(ROOT, 'watchlist.json')

# Discord ANSI colors for ```ansi blocks
_ANSI = {
    'Prime': '\033[1;35m',  # bold magenta
    'STR':   '\033[1;31m',  # bold red
    'RVOL':  '\033[1;34m',  # bold blue
    'RSM':   '\033[1;32m',  # bold green
    'SMA50': '\033[1;33m',  # bold yellow
    'RESET': '\033[0m',
}

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--discord', action='store_true', help='Send results to Discord')
parser.add_argument('--loop',    action='store_true', help='Run every 30min during market hours')
args = parser.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────────────
def bkk_now() -> datetime:
    return datetime.now(BKK)


def in_market_hours() -> bool:
    now = bkk_now()
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    morning   = (10, 0) <= t <= (12, 30)
    afternoon = (14, 0) <= t <= (16, 30)
    return morning or afternoon


def minutes_elapsed() -> float:
    """Minutes since market open today."""
    now = bkk_now()
    open_dt = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    elapsed = (now - open_dt).total_seconds() / 60
    return max(elapsed, 1)


def projected_rvol(current_volume: float, avg_volume: float) -> float:
    """Project full-day RVol based on current volume and time elapsed."""
    if avg_volume <= 0:
        return 0.0
    minutes_open  = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1] - MARKET_OPEN[0] * 60 - MARKET_OPEN[1]
    elapsed       = minutes_elapsed()
    pace_factor   = minutes_open / elapsed
    return (current_volume * pace_factor) / avg_volume


def set_tick(price: float) -> float:
    if price < 2:    return 0.01
    if price < 5:    return 0.02
    if price < 10:   return 0.05
    if price < 25:   return 0.10
    if price < 100:  return 0.25
    if price < 200:  return 0.50
    if price < 400:  return 1.00
    return 2.00


def load_watchlist() -> list:
    if not os.path.exists(WL_PATH):
        print(f'  No watchlist.json found at {WL_PATH}')
        print(f'  Run main.py first to generate it.')
        return []
    with open(WL_PATH) as f:
        wl = json.load(f)
    today = str(date.today())
    # Warn if watchlist is stale
    dates = set(w.get('date_added', '') for w in wl)
    if today not in dates:
        print(f'  ⚠ Watchlist last updated: {max(dates)} (today is {today})')
    return wl


def fetch_intraday(ticker: str) -> pd.DataFrame | None:
    """Download 5d of daily data — enough to get today's intraday + recent avg volume."""
    try:
        df = yf.download(ticker, period='1mo', interval='1d',
                         auto_adjust=True, progress=False, show_errors=False)
        if df is None or len(df) < 5:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={'Open':'Open','High':'High','Low':'Low',
                                'Close':'Close','Volume':'Volume'})
        return df
    except Exception:
        return None


def check_stock(w: dict, df: pd.DataFrame) -> dict | None:
    """
    Check if price broke above the watchlist level today.
    Returns signal dict if breakout detected, else None.
    """
    level    = w['level']
    ticker   = w['ticker']
    kind     = w['kind']
    rsm      = w.get('rsm', 0)
    atr      = w.get('atr', 0)

    if len(df) < 2:
        return None

    last     = df.iloc[-1]
    prev     = df.iloc[-2]
    cl       = float(last['Close'])
    prev_cl  = float(prev['Close'])
    hi       = float(last['High'])
    vol      = float(last['Volume'])
    op       = float(last['Open'])

    # Must have broken above level today
    broke = cl > level and prev_cl <= level
    # Also catch intraday break (high crossed even if close hasn't yet)
    intraday_break = hi > level and prev_cl <= level

    if not (broke or intraday_break):
        return None

    # Avg volume from recent bars (exclude today)
    avg_vol = float(df['Volume'].iloc[:-1].tail(20).mean()) if len(df) > 1 else 0

    # Projected RVol
    proj_rvol = projected_rvol(vol, avg_vol)
    cur_rvol  = vol / avg_vol if avg_vol > 0 else 0

    # Entry price
    entry = max(round(level + set_tick(level), 6), op)

    # SMA50
    sma50 = float(df['Close'].tail(50).mean()) if len(df) >= 50 else None

    # Stretch
    stretch = 0.0
    if sma50 and atr > 0 and sma50 > 0:
        atr_pct    = atr / level * 100
        price_dist = (level - sma50) / sma50 * 100
        stretch    = round(price_dist / atr_pct, 2) if atr_pct > 0 else 0

    # Criteria
    rvol_ok   = proj_rvol >= CFG['rvol_min']
    rsm_ok    = rsm >= CFG['rs_momentum_min']
    regime_ok = sma50 is not None and cl > sma50

    if stretch > 4:
        criteria = 'STR'
    elif rvol_ok and rsm_ok and regime_ok:
        criteria = 'Prime'
    elif rvol_ok and regime_ok:
        criteria = 'RVOL'
    elif rsm_ok and regime_ok:
        criteria = 'RSM'
    else:
        criteria = 'SMA50'

    confirmed = broke          # close already above level
    intraday  = not broke      # only high crossed, close not yet

    return dict(
        ticker     = ticker.replace('.BK', ''),
        ticker_full= ticker,
        kind       = 'Hz' if kind == 'hz' else 'TL',
        level      = level,
        close      = cl,
        entry      = entry,
        cur_rvol   = round(cur_rvol, 2),
        proj_rvol  = round(proj_rvol, 2),
        rsm        = rsm,
        atr        = atr,
        atr_pct    = round(atr / cl * 100, 2) if cl > 0 else 0,
        stretch    = stretch,
        criteria   = criteria,
        confirmed  = confirmed,
        intraday   = intraday,
        rvol_ok    = rvol_ok,
        rsm_ok     = rsm_ok,
        regime_ok  = regime_ok,
    )


# ── Discord ───────────────────────────────────────────────────────────────────
def send_discord_alert(signals: list, now: datetime):
    load_dotenv(os.path.join(ROOT, '.env'))
    url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    if not url:
        print('  DISCORD_WEBHOOK not set.')
        return

    time_str = now.strftime('%H:%M')
    date_str = now.strftime('%Y-%m-%d')
    n        = len(signals)

    header = (
        f"**⚡ INTRADAY  |  {date_str}  {time_str} BKK**\n"
        f"`{n} signal{'s' if n!=1 else ''}`"
    )

    # Group by criteria, Prime first then RVOL
    groups = {'Prime': [], 'RVOL': []}
    for s in sorted(signals, key=lambda x: x['ticker']):
        if s['criteria'] in groups:
            groups[s['criteria']].append(s)

    col_prime = _ANSI['Prime']
    col_rvol  = _ANSI['RVOL']
    rst       = _ANSI['RESET']

    lines = []
    for crit, col in [('Prime', col_prime), ('RVOL', col_rvol)]:
        if not groups[crit]:
            continue
        lines.append(f'{col}{crit}{rst}')
        for s in groups[crit]:
            str_disp = f"{s['stretch']:.1f}x" if s['stretch'] else '—'
            lines.append(
                f"{s['ticker']} | broke ฿{s['level']:.2f} → now ฿{s['close']:.2f}"
                f"  RVol {s['cur_rvol']:.1f}x (proj {s['proj_rvol']:.1f}x)"
                f"  RSM {s['rsm']:.0f}  STR {str_disp}"
            )
        lines.append('')  # blank line between groups

    block = '```ansi\n' + '\n'.join(lines).rstrip() + f'\n{rst}```'

    for msg in [header, block]:
        try:
            requests.post(url, json={'content': msg}, timeout=10)
            time.sleep(0.5)
        except Exception as e:
            print(f'  Discord error: {e}')


# ── Main scan ─────────────────────────────────────────────────────────────────
def run_scan():
    now       = bkk_now()
    watchlist = load_watchlist()
    if not watchlist:
        return

    # Deduplicate tickers
    tickers = list({w['ticker'] for w in watchlist})
    print(f'\n  [{now.strftime("%H:%M")}] Scanning {len(tickers)} watchlist stocks...')

    # Download data for all tickers
    dfs = {}
    for ticker in tickers:
        df = fetch_intraday(ticker)
        if df is not None:
            dfs[ticker] = df
        time.sleep(0.1)

    # Check each watchlist level
    signals = []
    for w in watchlist:
        df = dfs.get(w['ticker'])
        if df is None:
            continue
        sig = check_stock(w, df)
        if sig:
            signals.append(sig)

    # Deduplicate (same ticker may have hz + tl level)
    seen = set()
    unique_signals = []
    for s in signals:
        key = (s['ticker'], s['level'])
        if key not in seen:
            seen.add(key)
            unique_signals.append(s)

    # ── Print all to terminal ─────────────────────────────────────────────
    if not unique_signals:
        print(f'  No breakouts detected.')
        return

    HDR = f"  {'Ticker':<7}  {'T':<3}  {'Crit':<6}  {'Level':>7}  {'Close':>7}  {'RVol':>6}  {'Proj':>6}  {'RSM':>4}  {'STR':>5}"
    DIV = '  ' + '─' * 64
    print(f'\n  {len(unique_signals)} BREAKOUT(S) DETECTED')
    print(HDR); print(DIV)
    last_crit = None
    sort_key  = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}
    for s in sorted(unique_signals, key=lambda x: (sort_key.get(x['criteria'], 9), x['ticker'])):
        if last_crit is not None and s['criteria'] != last_crit:
            print()
        last_crit = s['criteria']
        str_disp  = f"{s['stretch']:.1f}x" if s['stretch'] else '—'
        print(f"  {s['ticker']:<7}  {s['kind']:<3}  {s['criteria']:<6}  "
              f"{s['level']:>7.2f}  {s['close']:>7.2f}  "
              f"{s['cur_rvol']:>5.1f}x  {s['proj_rvol']:>5.1f}x  "
              f"{s['rsm']:>4.0f}  {str_disp:>5}")

    # ── Discord: Prime and RVOL only ──────────────────────────────────────
    if args.discord:
        alert_signals = [s for s in unique_signals if s['criteria'] in ('Prime', 'RVOL')]
        if alert_signals:
            send_discord_alert(alert_signals, now)
            print(f'  ✅ Discord sent ({len(alert_signals)} Prime/RVOL signals)')
        else:
            print(f'  No Prime/RVOL signals — Discord skipped')


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if args.loop:
        print(f'  Intraday scanner running — every {LOOP_INTERVAL//60}min during market hours')
        while True:
            if in_market_hours():
                run_scan()
            else:
                now = bkk_now()
                print(f'  [{now.strftime("%H:%M")}] Market closed — waiting...')
            time.sleep(LOOP_INTERVAL)
    else:
        run_scan()