"""
Macro Map API — serves a cached global-markets snapshot, refreshed on TTL.
  GET /api/macro
"""

from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.macro import build_macro_payload

router = APIRouter()

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MACRO_CACHE = os.path.join(_ROOT, 'data', 'macro.json')
_TTL_SECONDS = 30 * 60
_fetch_lock = threading.Lock()


def _cache_age_s() -> float | None:
    if not os.path.exists(_MACRO_CACHE):
        return None
    return datetime.now(timezone.utc).timestamp() - os.path.getmtime(_MACRO_CACHE)


def _read_cache() -> dict | None:
    try:
        with open(_MACRO_CACHE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(payload: dict) -> None:
    os.makedirs(os.path.dirname(_MACRO_CACHE), exist_ok=True)
    with open(_MACRO_CACHE, 'w', encoding='utf-8') as f:
        json.dump(payload, f)


def _cache_fresh() -> dict | None:
    age = _cache_age_s()
    if age is not None and age < _TTL_SECONDS:
        cached = _read_cache()
        if cached:
            return cached
    return None


@router.get('/macro')
def get_macro():
    fresh = _cache_fresh()
    if fresh:
        return fresh

    # Serialize cache-miss fetches — two requests racing a stale/cold cache
    # would otherwise both trigger the full ~37-ticker yfinance fetch.
    with _fetch_lock:
        # re-check: whoever held the lock first may have just refreshed it
        fresh = _cache_fresh()
        if fresh:
            return fresh

        payload = build_macro_payload()
        if payload.get('indices'):
            _write_cache(payload)
            return payload

        # fetch failed (offline / yfinance down) — serve stale cache if we have one
        cached = _read_cache()
        return cached or payload
