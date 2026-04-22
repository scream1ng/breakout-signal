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

from fastapi import APIRouter

router = APIRouter()

# Path to the JSON file written by main.py after each EOD scan
_ROOT             = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCAN_RESULTS     = os.path.join(_ROOT, 'data', 'scan_results.json')


def _read_scan() -> dict | None:
    """Return parsed scan_results.json or None if unavailable."""
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
    groups: dict[str, list] = {}
    for item in items:
        g = item.get('ma_group', 'Other')
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
