from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import main_app
from app.scheduler.runner import _as_utc


def test_as_utc_handles_naive_and_aware():
    naive = datetime(2026, 4, 23, 10, 0, 0)
    aware = datetime(2026, 4, 23, 10, 0, 0, tzinfo=timezone.utc)

    n = _as_utc(naive)
    a = _as_utc(aware)

    assert n.tzinfo is not None
    assert a.tzinfo is not None
    assert n.utcoffset().total_seconds() == 0
    assert a.utcoffset().total_seconds() == 0


def test_api_smoke_endpoints():
    with TestClient(main_app.app) as client:
        r = client.get('/')
        assert r.status_code == 200

        r = client.get('/api/system')
        assert r.status_code == 200
        body = r.json()
        assert 'scheduler_running' in body
        assert 'recent_history' in body

        r = client.get('/api/signals')
        assert r.status_code == 200
        body = r.json()
        assert 'watchlist' in body
        assert 'alerted_today' in body

        r = client.get('/api/portfolio')
        assert r.status_code == 200
        body = r.json()
        assert 'open_positions' in body
        assert 'recent_closed' in body

        r = client.get('/api/scan/latest')
        assert r.status_code == 200

        r = client.get('/api/backtest')
        assert r.status_code == 200

        r = client.get('/api/watchlist/detail')
        assert r.status_code == 200
        body = r.json()
        items = body.get('items', [])
        keys = [str(i.get('ticker_full') or i.get('ticker') or '').upper() for i in items]
        keys = [k for k in keys if k]
        assert len(keys) == len(set(keys))


def test_manual_close_endpoint_safe_response():
    with TestClient(main_app.app) as client:
        r = client.post('/api/trades/close', json={'ticker': 'NOTFOUND.BK', 'reason': 'MANUAL'})
        # In paper mode this should be 404 if not found.
        # If runtime mode is changed to live, endpoint correctly returns 503.
        assert r.status_code in (404, 503)
