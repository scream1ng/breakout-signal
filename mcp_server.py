"""
mcp_server.py — read-only MCP server over the deployed breakout-signal REST API.

Two entry points, same tools:
  stdio  — `.venv/bin/python mcp_server.py`, wired up by .mcp.json for Claude Code.
  HTTP   — `http_app` below, dispatched at /mcp by asgi.py for claude.ai.

Every tool filters and trims server-side so a single call never dumps the full
multi-hundred-KB scan payload into the context.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

BASE = os.getenv('APP_BASE_URL', 'https://breakout-signal.up.railway.app').rstrip('/')
MAX_LIMIT = 50
_TTL = 120          # seconds — one scan/day, so a short cache is plenty
_cache: dict[str, tuple[float, dict]] = {}

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

mcp = MCPServer(
    name='breakout-signal',
    instructions='Read-only access to the Thai SET breakout scanner. '
                 'Signals are EOD close-qualified; intraday fires are separate.',
)


def _get(path: str) -> dict:
    """GET /api/{path} with a short TTL cache. Raises on transport failure."""
    hit = _cache.get(path)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    url = f'{BASE}/api/{path}'
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    _cache[path] = (time.time(), data)
    return data


def _cap(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def _pick(row: dict, keys: tuple[str, ...]) -> dict:
    return {k: row[k] for k in keys if k in row}


def _trim(rows: list[dict], keys: tuple[str, ...], limit: int) -> dict:
    capped = _cap(limit)
    return {'total': len(rows), 'returned': min(len(rows), capped),
            'rows': [_pick(r, keys) for r in rows[:capped]]}


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
def get_scan_summary() -> dict:
    """Latest EOD scan: date, universe size, signal/watchlist counts, and the
    overall backtest stats for that run. Start here to see how fresh data is."""
    d = _get('scan/latest')
    return {
        'date': d.get('date'),
        'created_at': d.get('created_at'),
        'n_stocks': d.get('n_stocks'),
        'n_signals': d.get('n_signals'),
        'n_watching': d.get('n_watching'),
        'overall_bt': d.get('overall_bt'),
        'base_url': BASE,
    }


@mcp.tool(annotations=READ_ONLY)
def list_signals(source: str = 'eod', label: str = '', min_rsm: float = 0.0,
                 limit: int = 25) -> dict:
    """Triggered breakouts.

    source: 'eod' for close-qualified signals from the last EOD scan,
            'intraday' for today's live intraday fires.
    label:  filter by criteria — Prime, RVOL, RSM, STR, SMA50. Empty = all.
    min_rsm: keep only rows with RS Momentum at or above this.
    """
    if source == 'intraday':
        rows = _get('signals').get('alerted_today', [])
        keys = ('ticker', 'sector', 'criteria', 'kind', 'level', 'close',
                'rsm', 'proj_rvol', 'stretch', 'alerted_at')
    elif source == 'eod':
        rows = _get('scan/latest').get('signals', [])
        keys = ('ticker', 'sector', 'criteria', 'kind', 'date', 'bp', 'close',
                'sl', 'tp1', 'tp2', 'rsm', 'rvol', 'stretch', 'atr')
    else:
        return {'error': "source must be 'eod' or 'intraday'"}

    if label:
        want = label.strip().upper()
        rows = [r for r in rows if str(r.get('criteria', '')).upper() == want]
    if min_rsm:
        rows = [r for r in rows if (r.get('rsm') or 0) >= min_rsm]
    rows.sort(key=lambda r: r.get('rsm') or 0, reverse=True)
    return {'source': source, **_trim(rows, keys, limit)}


@mcp.tool(annotations=READ_ONLY)
def get_watchlist(ma_group: str = '', min_rsm: float = 0.0,
                  limit: int = 25) -> dict:
    """Stocks sitting near a breakout level, sorted by RS Momentum.

    ma_group: filter by moving-average position — '> MA10', '> MA20', '> MA50'.
    """
    d = _get('watchlist/detail')
    rows = d.get('items', [])
    if ma_group:
        rows = [r for r in rows if r.get('ma_group') == ma_group]
    if min_rsm:
        rows = [r for r in rows if (r.get('rsm') or 0) >= min_rsm]
    rows.sort(key=lambda r: r.get('rsm') or 0, reverse=True)
    keys = ('ticker', 'sector', 'close', 'rsm', 'rvol', 'stretch', 'atr',
            'sma50', 'ma_group', 'above_ema10', 'above_ema20', 'levels',
            'date_added', 'broke')
    groups = {k: len(v) for k, v in (d.get('groups') or {}).items()}
    return {'date': d.get('date'), 'group_counts': groups,
            **_trim(rows, keys, limit)}


@mcp.tool(annotations=READ_ONLY)
def get_backtest(ticker: str = '', sort_by: str = 'pnl_pct',
                 limit: int = 25) -> dict:
    """Per-ticker backtest results from the last EOD scan.

    ticker: one symbol (e.g. TOP) returns its full row including the per-label
            breakdown. Empty returns a ranked slice.
    sort_by: pnl_pct, wr, trades, or rsm.
    """
    d = _get('backtest')
    rows = d.get('rows', [])
    if ticker:
        want = ticker.strip().upper().removesuffix('.BK')
        match = next((r for r in rows if str(r.get('ticker', '')).upper() == want), None)
        return match or {'error': f'{want} not in the last scan universe',
                         'universe_size': len(rows)}
    if sort_by not in ('pnl_pct', 'wr', 'trades', 'rsm'):
        return {'error': 'sort_by must be pnl_pct, wr, trades, or rsm'}
    rows = sorted(rows, key=lambda r: r.get(sort_by) or 0, reverse=True)
    keys = ('ticker', 'sector', 'trades', 'wr', 'pnl_pct', 'rsm',
            'has_signal', 'has_pending')
    return {'date': d.get('date'), 'overall_bt': d.get('overall_bt'),
            'sort_by': sort_by, **_trim(rows, keys, limit)}


@mcp.tool(annotations=READ_ONLY)
def get_screener(sector: str = '', limit: int = 25) -> dict:
    """RS Momentum universe. With no sector, returns sector-level rotation.
    With a sector id (e.g. 'energyminerals'), returns its member stocks."""
    d = _get('screener')
    meta = {'date': d.get('date'), 'total': d.get('total'),
            'median_rsm100': d.get('median_rsm100'),
            'median_rsm21': d.get('median_rsm21')}
    stock_keys = ('tk', 'sectorName', 'rsm100', 'rsm21', 'm1', 'off', 'lead')
    if sector:
        want = sector.strip().lower().replace(' ', '')
        rows = [s for s in d.get('stocks', [])
                if str(s.get('sector', '')).lower() == want]
        if not rows:
            ids = sorted({s.get('sector') for s in d.get('stocks', [])})
            return {'error': f'no sector {want}', 'valid_sectors': ids}
        rows.sort(key=lambda r: r.get('rsm100') or 0, reverse=True)
        return {**meta, 'sector': want, **_trim(rows, stock_keys, limit)}
    sectors = [{k: s[k] for k in ('id', 'name', 'abbr') if k in s}
               | {'n_members': len(s.get('members') or [])}
               for s in d.get('sectors', [])]
    return {**meta, 'sectors': sectors}


@mcp.tool(annotations=READ_ONLY)
def get_job_health(limit: int = 10) -> dict:
    """Scheduler state and recent job runs. Use to check whether the data
    behind the other tools is actually being refreshed on schedule."""
    d = _get('system')
    keys = ('id', 'job_name', 'status', 'started_at', 'duration_s',
            'stocks_scanned', 'signals_found', 'error')
    history = d.get('recent_history', [])
    failures = [_pick(r, keys) for r in history if r.get('status') == 'failed']
    return {
        'scheduler_running': d.get('scheduler_running'),
        'next_runs': d.get('next_runs'),
        'last_runs': {k: _pick(v, keys) for k, v in (d.get('last_runs') or {}).items()},
        'n_failed_in_history': len(failures),
        'failures': failures[:_cap(limit)],
        **_trim(history, keys, limit),
    }


# ── HTTP transport ────────────────────────────────────────────────────────────
# Built at import time so asgi.py can dispatch to it. stateless_http means each
# request stands alone rather than being pinned to a session id the server has
# to keep alive between calls — the session manager still has to be running,
# see session_manager_lifespan below.
#
# transport_security: the default host 127.0.0.1 auto-enables DNS-rebinding
# protection allow-listing only localhost, so every request carrying the Railway
# domain as Host is rejected with 421. Nothing here is writable or private — the
# same data is already served unauthenticated over /api — so the localhost-only
# check buys nothing.
http_app = mcp.streamable_http_app(
    streamable_http_path='/mcp',
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_session_started = False


@asynccontextmanager
async def session_manager_lifespan():
    """Start the session manager, which /mcp needs even when stateless.

    The manager refuses a second .run() on the same instance. A deployed
    process enters the app lifespan exactly once, but the test suite opens
    more than one TestClient against the same app object, so re-entry is a
    no-op rather than a crash. Tests do not exercise /mcp.
    """
    global _session_started
    if _session_started:
        yield
        return
    _session_started = True
    async with mcp.session_manager.run():
        yield


if __name__ == '__main__':
    mcp.run('stdio')
