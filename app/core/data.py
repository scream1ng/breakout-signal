"""
core/data.py — Price data download with daily caching
  Cache stored as pickle files in cache/ folder.
  Cache valid all day; expires once per day after SET closes (16:30 Bangkok / UTC+7).
  First run after 16:30 re-downloads everything. Subsequent runs reuse until midnight.
  Uses pickle (no extra dependencies required).
"""

import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# Bangkok = UTC+7
BKK_TZ       = timezone(timedelta(hours=7))
MARKET_CLOSE = 16 * 60 + 30   # 16:30 in minutes since midnight


def _bkk_now() -> datetime:
    return datetime.now(BKK_TZ)


def _cache_path(ticker: str) -> str:
    safe = ticker.replace('.', '_').replace('^', 'IDX_')
    return os.path.join(CACHE_DIR, f'{safe}.pkl')


def _cache_valid(path: str) -> bool:
    """Cache is valid only after market close and if saved after close.
    Before close: always re-download (intraday data changes every run).
    In CI (GitHub Actions): always re-download.
    """
    if os.environ.get('CI'):
        return False   # always fresh on GitHub Actions
    if not os.path.exists(path):
        return False

    now      = _bkk_now()
    mtime_ts = os.path.getmtime(path)
    mtime    = datetime.fromtimestamp(mtime_ts, tz=BKK_TZ)

    now_mins   = now.hour * 60 + now.minute
    mtime_mins = mtime.hour * 60 + mtime.minute

    # Before market close: never use cache — prices are still changing
    if now_mins < MARKET_CLOSE:
        return False

    # After market close: cache must be from today AND saved after close
    return mtime.date() == now.date() and mtime_mins >= MARKET_CLOSE


def load_ticker(ticker: str, period: str = '2y', force: bool = False) -> pd.DataFrame | None:
    """Load OHLCV for ticker. Uses cache when valid; downloads otherwise."""
    path = _cache_path(ticker)

    if not force and _cache_valid(path):
        try:
            df = pd.read_pickle(path)
            return df
        except Exception:
            pass  # corrupt cache → re-download

    # Download fresh via Settrade, with a fallback to yfinance
    try:
        from app.core.settrade_client import get_market_data
        market = get_market_data()
        symbol = ticker.replace('.BK', '')
        if symbol == '^SET':
            symbol = '.SET'
            
        candles = market.get_candlestick(symbol=symbol, interval="1d", limit=500)
        df_new = pd.DataFrame(candles)
        df_new['time'] = pd.to_datetime(df_new['time'], unit='s')
        df_new.set_index('time', inplace=True)
        df_new.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        df = df_new[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
        
    except Exception as e:
        # Fallback to yfinance if API key is invalid or SETTRADE is down
        # print(f"  [data] Settrade failed for {ticker} ({e}). Falling back to yfinance.")
        try:
            raw = yf.download(ticker, period='2y', interval='1d',
                              auto_adjust=True, progress=False)
            if raw is None or raw.empty:
                return None
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            if 'Close' not in raw.columns:
                return None
            df = raw[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
            df.index = pd.to_datetime(df.index)
        except Exception:
            return None

    if len(df) < 60:
        return None

    # Save to cache
    try:
        df.to_pickle(path)
    except Exception as e:
        print(f'  [cache] Could not save {ticker}: {e}')

    return df


def load_benchmark(cfg: dict, force: bool = False) -> pd.Series | None:
    """Load benchmark close series (e.g. ^SET.BK)."""
    ticker = cfg.get('benchmark', '^SET.BK')
    df = load_ticker(ticker, force=force)
    if df is None:
        return None
    return df['Close']


def cache_stats() -> dict:
    """Return info about current cache state."""
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith('.pkl')]
    now   = _bkk_now()
    valid = sum(1 for f in files if _cache_valid(os.path.join(CACHE_DIR, f)))
    return dict(total=len(files), valid=valid, bkk_time=now.strftime('%H:%M'), dir=CACHE_DIR)


def clear_cache():
    """Delete all cached files."""
    removed = 0
    for f in os.listdir(CACHE_DIR):
        if f.endswith('.pkl') or f.endswith('.parquet'):
            os.remove(os.path.join(CACHE_DIR, f))
            removed += 1
    print(f'  Cleared {removed} cached files from {CACHE_DIR}')