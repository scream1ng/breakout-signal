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

    watchlist    = _read_json(watchlist_path,   {'stocks': [], 'updated_at': None})
    alert_state  = _read_json(alert_state_path, {'date': None, 'alerted': [], 'failed': []})

    return {
        'watchlist':     watchlist.get('stocks', []),
        'watchlist_date': watchlist.get('updated_at') or watchlist.get('date'),
        'alerted_today': alert_state.get('alerted', []),
        'failed_today':  alert_state.get('failed', []),
        'alert_date':    alert_state.get('date'),
    }
