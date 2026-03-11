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
    """Cache is valid if file exists, saved today, and either:
    - market hasn't closed yet, OR file was saved after market close.
    In CI (GitHub Actions) cache is never valid — always re-download.
    """
    if os.environ.get('CI'):
        return False   # always fresh on GitHub Actions
    if not os.path.exists(path):
        return False

    now      = _bkk_now()
    mtime_ts = os.path.getmtime(path)
    mtime    = datetime.fromtimestamp(mtime_ts, tz=BKK_TZ)

    # Must be saved today
    if mtime.date() != now.date():
        return False

    now_mins   = now.hour * 60 + now.minute
    mtime_mins = mtime.hour * 60 + mtime.minute

    # Before market close: any cache from today is fine
    if now_mins < MARKET_CLOSE:
        return True

    # After market close: cache must have been saved after close to have EOD data
    return mtime_mins >= MARKET_CLOSE


def load_ticker(ticker: str, period: str = '2y', force: bool = False) -> pd.DataFrame | None:
    """Load OHLCV for ticker. Uses cache when valid; downloads otherwise."""
    path = _cache_path(ticker)

    if not force and _cache_valid(path):
        try:
            df = pd.read_pickle(path)
            return df
        except Exception:
            pass  # corrupt cache → re-download

    # Download fresh
    try:
        raw = yf.download(ticker, period='2y', interval='1d',
                          auto_adjust=True, progress=False)
    except Exception as e:
        return None

    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if 'Close' not in raw.columns:
        return None

    df = raw[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
    df.index = pd.to_datetime(df.index)
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