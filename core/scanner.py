"""
scanner.py — data fetching
  fetch_tv_stocks(cfg)  : pull SET stock list from TradingView scanner
  load_benchmark(cfg)   : download benchmark OHLCV via yfinance
"""

import sys
import warnings
import requests
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')


def fetch_tv_stocks(cfg: dict) -> list[dict]:
    """Return list of dicts {ticker, desc, sector, price} that pass the pre-screen."""
    min_turnover = cfg['min_turnover']
    print('  Fetching SET stocks from TradingView...')
    url     = 'https://scanner.tradingview.com/thailand/scan'
    payload = {
        'filter': [{'left': 'type', 'operation': 'equal', 'right': 'stock'}],
        'columns': ['name', 'description', 'sector', 'close',
                    'average_volume_10d_calc', 'SMA50', 'volume'],
        'sort':    {'sortBy': 'name', 'sortOrder': 'asc'},
        'range':   [0, 3000],
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        sys.exit(f'  ERROR: TradingView fetch failed: {e}')

    rows = []
    for item in resp.json().get('data', []):
        d = item['d']
        ticker  = d[0]; desc = d[1]; sector = d[2] or 'Unknown'
        price   = d[3] or 0; avg_vol = d[4] or 0; sma50 = d[5]
        if any(x in ticker for x in ['.F', '.R', '-W', '-R']):
            continue
        if price * avg_vol < min_turnover:
            continue
        if sma50 and price < sma50:
            continue
        rows.append({'ticker': f'{ticker}.BK', 'desc': desc or ticker,
                     'sector': sector, 'price': price})
    print(f'  -> {len(rows)} stocks pass pre-screen')
    return rows


def load_benchmark(cfg: dict) -> pd.Series:
    """Download 2y of daily closes for the benchmark index."""
    benchmark = cfg['benchmark']
    print(f'  Downloading benchmark {benchmark}...')
    br = yf.download(benchmark, period='2y', interval='1d',
                     auto_adjust=True, progress=False)
    if br.empty:
        sys.exit(f'  ERROR: Cannot download {benchmark}')
    if isinstance(br.columns, pd.MultiIndex):
        br.columns = br.columns.get_level_values(0)
    bench = br['Close'].dropna()
    print(f'  Benchmark: {len(bench)} bars')
    return bench
