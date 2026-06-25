"""
Scan results API — serves the latest EOD scan output from data/scan_results.json.
Endpoints:
  GET /api/scan/latest       — metadata summary
  GET /api/backtest          — per-ticker backtest table
  GET /api/watchlist/detail  — detailed watchlist grouped by MA position
"""

from __future__ import annotations
import json
import os
from datetime import datetime
import pytz

import pandas as pd
from fastapi import APIRouter, Query

router = APIRouter()

# Path to the JSON file written by main.py after each EOD scan
_ROOT             = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCAN_RESULTS     = os.path.join(_ROOT, 'data', 'scan_results.json')
_LIVE_PRICES      = os.path.join(_ROOT, 'data', 'watchlist_live.json')


def _read_live_prices() -> dict:
    """Return live price dict keyed by ticker if written today (BKK)."""
    if not os.path.exists(_LIVE_PRICES):
        return {}
    today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')
    try:
        with open(_LIVE_PRICES, encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict) and raw.get('date') == today:
            return raw.get('prices', {})
    except Exception:
        pass
    return {}


def _merge_live(items: list[dict], live: dict) -> list[dict]:
    if not live:
        return items
    merged = []
    for item in items:
        ticker = item.get('ticker_full') or item.get('ticker', '')
        lp = live.get(ticker)
        if lp:
            item = dict(item, close=lp['close'], rvol=lp['rvol'], broke=lp.get('broke', False))
        merged.append(item)
    return merged


def _read_scan() -> dict | None:
    """Return latest scan snapshot. Tries DB (scan_snapshots) first, falls back to JSON."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import ScanSnapshot
        init_db()
        db = SessionLocal()
        try:
            row = db.query(ScanSnapshot).order_by(ScanSnapshot.scan_date.desc()).first()
            if row:
                return json.loads(row.data_json)
        finally:
            db.close()
    except Exception:
        pass
    # JSON fallback (local dev)
    if not os.path.exists(_SCAN_RESULTS):
        return None
    try:
        with open(_SCAN_RESULTS, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


# ── GET /api/scan/latest ──────────────────────────────────────────────────────
@router.get('/scan/latest')
def get_scan_latest():
    data = _read_scan()
    if not data:
        return {'date': None, 'n_stocks': 0, 'n_signals': 0, 'n_watching': 0,
                'overall_bt': None, 'signals': []}
    keys = ('date', 'created_at', 'n_stocks', 'n_signals', 'n_watching', 'overall_bt', 'signals')
    return {k: data[k] for k in keys if k in data}


# ── GET /api/backtest ─────────────────────────────────────────────────────────
@router.get('/backtest')
def get_backtest():
    data = _read_scan()
    if not data:
        return {'date': None, 'overall_bt': None, 'rows': [], 'intraday_bt': None}
    return {
        'date':       data.get('date'),
        'overall_bt': data.get('overall_bt'),
        'rows':       data.get('backtest_rows', []),
        'intraday_bt': data.get('intraday_bt'),
    }


# ── GET /api/watchlist/detail ─────────────────────────────────────────────────
@router.get('/watchlist/detail')
def get_watchlist_detail():
    data = _read_scan()
    if not data:
        return {'date': None, 'items': [], 'groups': {}, 'copy_str': ''}
    items = data.get('watchlist', [])
    deduped_items: list[dict] = []
    seen_tickers: set[str] = set()
    for item in items:
        t = str(item.get('ticker_full') or item.get('ticker') or '').upper()
        if not t:
            continue
        if t in seen_tickers:
            continue
        seen_tickers.add(t)
        deduped_items.append(item)

    items = deduped_items
    groups: dict[str, list] = {}

    def _normalize_group(raw: str | None) -> str:
        text = str(raw or '').upper().replace(' ', '')
        if 'MA10' in text or 'EMA10' in text:
            return '> MA10'
        if 'MA20' in text or 'EMA20' in text:
            return '> MA20'
        if 'MA50' in text or 'SMA50' in text:
            return '> MA50'
        return 'Other'

    def _group_from_item(item: dict) -> str:
        if item.get('ma_group'):
            return _normalize_group(item.get('ma_group'))
        if item.get('above_ema10') or item.get('above_ma10'):
            return '> MA10'
        if item.get('above_ema20') or item.get('above_ma20'):
            return '> MA20'
        if item.get('above_sma50') or item.get('above_ma50'):
            return '> MA50'
        return 'Other'

    live = _read_live_prices()
    items = _merge_live(items, live)

    for item in items:
        g = _group_from_item(item)
        groups.setdefault(g, []).append(item)
    # Build TradingView copy string: ###> MA10,SET:A,SET:B,###> MA20,...
    parts: list[str] = []
    for label in ('> MA10', '> MA20', '> MA50', 'Other'):
        grp = groups.get(label, [])
        if grp:
            parts.append('###' + label)
            for it in grp:
                tf = it.get('ticker_full', it.get('ticker', ''))
                # Convert X.BK → SET:X
                if tf.endswith('.BK'):
                    parts.append('SET:' + tf[:-3])
                elif tf.endswith('.AX'):
                    parts.append('ASX:' + tf[:-3])
                else:
                    parts.append(tf)
    copy_str = ','.join(parts)
    return {'date': data.get('date'), 'items': items, 'groups': groups, 'copy_str': copy_str}


def _rebuild_chart_basic(ticker_full: str, period: str = '2y') -> dict | None:
    """Fallback chart payload — candles + EMA10/EMA20/SMA50/SMA200 only.

    No breakout signals/trades/levels (those exist only for stored
    signal+watchlist tickers). Cheap pandas; no main.py / scan pipeline import.
    Shape matches get_chart_data() so the same renderer handles it.
    """
    from app.core.data import load_ticker
    try:
        df = load_ticker(ticker_full, period=period)
    except Exception:
        df = None
    if df is None or df.empty:
        return None
    df.index = pd.to_datetime(df.index)

    close = df['Close'].astype(float)
    vol   = df['Volume'].astype(float)
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    avgvol = vol.rolling(20).mean()
    rvol = (vol / avgvol).replace([float('inf')], 0).fillna(0)
    rvol_min = 1.5

    def _arr(s):
        return [None if pd.isna(v) else round(float(v), 4) for v in s]

    candles = []
    for i, (d, r) in enumerate(df.iterrows()):
        if pd.isna(r.Open) or pd.isna(r.Close):
            continue
        rv = round(float(rvol.iloc[i]), 2)
        up = float(r.Close) >= float(r.Open)
        candles.append({
            'i': i, 'd': str(d.date()),
            'o': round(float(r.Open), 4), 'h': round(float(r.High), 4),
            'l': round(float(r.Low), 4),  'c': round(float(r.Close), 4),
            'rv': rv,
            'col': ('#26a69a' if up else '#ef5350'),
        })
    if not candles:
        return None

    return {
        'ticker': ticker_full,
        'desc': ticker_full, 'sector': '',
        'candles': candles,
        'ema10': _arr(ema10), 'ema20': _arr(ema20),
        'sma50': _arr(sma50), 'sma200': _arr(sma200),
        'rsm': [None] * len(df), 'rvol': [round(float(v), 2) for v in rvol],
        'rvol_min': rvol_min, 'rsm_min': 80,
        'last_close': candles[-1]['c'],
        'hz_fast': [], 'hz_slow': [], 'tl_fast': [], 'tl_slow': [],
        'signals': [], 'trades': [],
        'partial': True,   # flag: candles+MAs only, no signals/levels
    }


# ── GET /api/chart/{ticker} ───────────────────────────────────────────────────
@router.get('/chart/{ticker}')
def get_chart(ticker: str, period: str = Query(default='2y')):
    """Return the full get_chart_data() dict for one ticker.

    Stored signal/watchlist tickers come from the ChartData table (with
    breakout signals + trade markers); any other ticker is rebuilt on the fly
    as candles + moving averages only.
    """
    from app.storage.state import load_chart, _norm_ticker
    tk = _norm_ticker(ticker)
    payload = load_chart(tk) or _rebuild_chart_basic(tk, period=period)
    if not payload:
        return {'ticker': ticker, 'candles': [], 'signals': [], 'trades': [], 'found': False}
    payload['live'] = _live_bar(tk)   # today's forming bar from intraday scan, or None
    return payload


def _live_bar(ticker_full: str) -> dict | None:
    """Today's live OHLC bar for one ticker, written by intraday.py. None if absent."""
    lp = _read_live_prices().get(ticker_full)
    if not lp:
        return None
    today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')
    c = lp['close']
    return {'date': today, 'o': lp.get('open', c), 'h': lp.get('high', c),
            'l': lp.get('low', c), 'c': c}
