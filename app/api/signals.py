"""
app/api/signals.py — GET /api/signals
=======================================
Returns today's triggered intraday breaks + the current EOD watchlist.
Data is read from the JSON files written by intraday.py / main.py.
"""

import os
import json
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

    watchlist_raw = _read_json(watchlist_path, {'stocks': [], 'updated_at': None})
    alert_raw     = _read_json(alert_state_path, {'date': None, 'alerted': [], 'failed': []})

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

    return {
        'watchlist':      watchlist_stocks,
        'watchlist_date': watchlist_date,
        'alerted_today':  alerted_today,
        'failed_today':   failed_today,
        'alert_date':     alert_date,
    }
