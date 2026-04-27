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

from fastapi import APIRouter

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
        return {'date': None, 'overall_bt': None, 'rows': []}
    return {
        'date':       data.get('date'),
        'overall_bt': data.get('overall_bt'),
        'rows':       data.get('backtest_rows', []),
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
