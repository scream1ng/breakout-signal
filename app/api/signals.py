"""
app/api/signals.py — GET /api/signals
=======================================
Returns today's triggered intraday breaks + the current EOD watchlist.
Data is read from the JSON files written by intraday.py / main.py.
"""

import os
import json
from datetime import datetime
import pytz
from fastapi import APIRouter

router = APIRouter()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_json(path: str, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return fallback


@router.get('/signals')
def get_signals():
    watchlist_path    = os.path.join(ROOT, 'data', 'watchlist.json')
    alert_state_path  = os.path.join(ROOT, 'data', 'alert_state.json')

    # DB first, JSON fallback
    _today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')
    watchlist_raw = None
    alert_raw = None
    try:
        from app.storage.state import load_state as db_load
        watchlist_raw = db_load('watchlist')
        alert_raw = db_load(f'alert_state:{_today}')
    except Exception:
        pass
    if watchlist_raw is None:
        watchlist_raw = _read_json(watchlist_path, {'stocks': [], 'updated_at': None})
    if alert_raw is None:
        alert_raw = _read_json(alert_state_path, {'date': None, 'alerted': [], 'failed': []})

    # Backward compatibility: some runs store watchlist.json as a plain list.
    if isinstance(watchlist_raw, list):
        watchlist_stocks = watchlist_raw
        watchlist_date = None
    elif isinstance(watchlist_raw, dict):
        watchlist_stocks = watchlist_raw.get('stocks', [])
        watchlist_date = watchlist_raw.get('updated_at') or watchlist_raw.get('date')
    else:
        watchlist_stocks = []
        watchlist_date = None

    if isinstance(alert_raw, dict):
        alerted_today = alert_raw.get('alerted', [])
        failed_today = alert_raw.get('failed', [])
        alert_date = alert_raw.get('date')
    else:
        alerted_today = []
        failed_today = []
        alert_date = None

    # Merge live prices written by intraday.py (same trading day only)
    _today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')
    live_path = os.path.join(ROOT, 'data', 'watchlist_live.json')
    live_raw  = _read_json(live_path, {})
    live_prices: dict = {}
    if isinstance(live_raw, dict) and live_raw.get('date') == _today:
        live_prices = live_raw.get('prices', {})

    if live_prices:
        merged = []
        for item in watchlist_stocks:
            ticker = item.get('ticker', '')
            lp = live_prices.get(ticker)
            if lp:
                item = dict(item, close=lp['close'], rvol=lp['rvol'], broke=lp.get('broke', False))
            merged.append(item)
        watchlist_stocks = merged

    return {
        'watchlist':      watchlist_stocks,
        'watchlist_date': watchlist_date,
        'alerted_today':  alerted_today,
        'failed_today':   failed_today,
        'alert_date':     alert_date,
    }
