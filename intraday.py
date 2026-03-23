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

BKK     = pytz.timezone('Asia/Bangkok')
WL_PATH = os.path.join(ROOT, 'watchlist.json')

_ANSI = {
    'Prime': '\033[1;35m',
    'RVOL':  '\033[1;34m',
    'RSM':   '\033[1;32m',
    'RESET': '\033[0m',
}

parser = argparse.ArgumentParser()
parser.add_argument('--discord', action='store_true')
args = parser.parse_args()


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


def proj_volume(cur_volume, avg_volume, now):
    """Project full morning session RVol (150min total: 10:00-12:30)."""
    if avg_volume <= 0:
        return 0.0
    open_min    = 10 * 60
    session_min = 150  # 2.5h morning session
    elapsed     = max(now.hour * 60 + now.minute - open_min, 1)
    elapsed     = min(elapsed, session_min)
    proj_vol    = cur_volume * session_min / elapsed
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


def criteria_label(rsm, rvol):
    rvol_ok = rvol >= CFG.get('rvol_min', 1.5)
    rsm_ok  = rsm  >= CFG.get('rs_momentum_min', 70)
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def send_discord(signals, now):
    load_dotenv(os.path.join(ROOT, '.env'))
    url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    if not url:
        print('  DISCORD_WEBHOOK not set.')
        return

    header = (
        f"**⚡ INTRADAY  |  {now.strftime('%Y-%m-%d')}  {now.strftime('%H:%M')} BKK**\n"
        f"`{len(signals)} signal{'s' if len(signals)!=1 else ''}`"
    )

    groups = {'Prime': [], 'RVOL': [], 'RSM': []}
    for s in sorted(signals, key=lambda x: x['ticker']):
        if s['criteria'] in groups:
            groups[s['criteria']].append(s)

    lines = []
    for crit in ('Prime', 'RVOL', 'RSM'):
        if not groups[crit]:
            continue
        col = _ANSI[crit]
        rst = _ANSI['RESET']
        lines.append(f'{col}{crit}{rst}')
        for s in groups[crit]:
            str_disp  = f"{s['stretch']:.1f}x" if s.get('stretch') else '—'
            lines.append(
                f"{s['ticker']} | broke ฿{s['level']:.2f} → now ฿{s['close']:.2f}"
                f"  RVol {s['cur_rvol']:.1f}x (proj {s['proj_rvol']:.1f}x)"
                f"  RSM {s['rsm']:.0f}  STR {str_disp}"
            )
        lines.append('')

    block = '```ansi\n' + '\n'.join(lines).rstrip() + f'\n{_ANSI["RESET"]}```'

    for msg in [header, block]:
        try:
            requests.post(url, json={'content': msg}, timeout=10)
            time.sleep(0.5)
        except Exception as e:
            print(f'  Discord error: {e}')


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

    tickers = list({w['ticker'] for w in watchlist})
    print(f'\n  [{now.strftime("%H:%M")}] Checking {len(tickers)} stocks...')

    # Batch download all tickers at once — faster, avoids rate limiting
    print(f'  Downloading data...', flush=True)
    data = {}
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
        crit     = criteria_label(w.get('rsm', 0), cur_rvol)

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
        alert = [s for s in signals if s['criteria'] in ('Prime', 'RVOL', 'RSM')]
        if alert:
            send_discord(alert, now)
            print(f'  ✅ Discord sent ({len(alert)} signals)')
        else:
            print('  No alertable signals — Discord skipped')


if __name__ == '__main__':
    run()
