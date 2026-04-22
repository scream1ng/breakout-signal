"""
run.py — Interactive launcher for Breakout Scanner
====================================================
Run this instead of calling main.py / intraday.py / backtest_optimize.py directly.

    python run.py
"""

import os
import sys
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON     = sys.executable


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def _ask(prompt, default=''):
    """Prompt with a default value shown in brackets."""
    suffix = f' [{default}]' if default else ''
    val = input(f'  {prompt}{suffix}: ').strip()
    return val if val else default


def _ask_yn(prompt, default='n'):
    """Yes/no prompt. Returns True for yes."""
    suffix = ' [y/N]' if default.lower() == 'n' else ' [Y/n]'
    val = input(f'  {prompt}{suffix}: ').strip().lower()
    if not val:
        return default.lower() == 'y'
    return val in ('y', 'yes')


def _run(cmd: list):
    """Run a command in the same terminal, inherit stdin/stdout."""
    try:
        subprocess.run([PYTHON] + cmd, cwd=SCRIPT_DIR)
    except KeyboardInterrupt:
        print('\n  Interrupted.')
    input('\n  Press Enter to return to menu...')


def _header():
    """Print the top banner with cache stats."""
    _clear()
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from app.core.data import cache_stats
        cs = cache_stats()
        cache_line = f'Cache: {cs["valid"]}/{cs["total"]} valid  BKK {cs["bkk_time"]}'
    except Exception:
        cache_line = ''

    date_str = datetime.today().strftime('%Y-%m-%d')
    print(f'\n{"=" * 56}')
    print(f'  BREAKOUT SCANNER  {date_str}')
    if cache_line:
        print(f'  {cache_line}')
    print(f'{"=" * 56}\n')


# ── Menu actions ──────────────────────────────────────────────────────────────

def action_scan():
    """End-of-day scan — build watchlist + HTML chart."""
    _header()
    print('  End-of-day Scan\n')

    period  = _ask('Period (6mo / 12mo / 2y)', '12mo')
    rsm     = _ask('Min RS Momentum', '80')
    discord = _ask_yn('Send to Discord?')

    cmd = ['main.py', '--period', period, '--rsm', rsm]
    if discord:
        cmd.append('--discord')

    print()
    _run(cmd)


def action_intraday():
    """Intraday check — scan watchlist for live signals."""
    _header()
    print('  Intraday Check\n')

    # Show watchlist age if available
    wl_path = os.path.join(SCRIPT_DIR, 'data', 'watchlist.json')
    if os.path.exists(wl_path):
        mtime   = datetime.fromtimestamp(os.path.getmtime(wl_path))
        age_hrs = (datetime.now() - mtime).total_seconds() / 3600
        print(f'  Watchlist last updated: {mtime.strftime("%Y-%m-%d %H:%M")}  ({age_hrs:.1f}h ago)')
        import json
        with open(wl_path) as f:
            wl = json.load(f)
        print(f'  Stocks in watchlist: {len(set(w["ticker"] for w in wl))}  ({len(wl)} levels)\n')
    else:
        print('  No watchlist found — run End-of-day scan first.\n')
        input('  Press Enter to return to menu...')
        return

    discord = _ask_yn('Send to Discord?')

    cmd = ['intraday.py']
    if discord:
        cmd.append('--discord')

    print()
    _run(cmd)


def action_view_all():
    """View charts — open today's HTML dashboard in browser."""
    _clear()
    print()
    _run(['main.py', '--view'])


def action_view_stock():
    """View single stock chart."""
    _header()
    print('  View Single Stock\n')

    ticker = _ask('Ticker (e.g. TOP, AOT, SCB)').upper()
    if not ticker:
        return

    period = _ask('Period (6mo / 12mo / 2y)', '12mo')

    _run(['main.py', '--view', ticker, '--period', period])


def action_optimize():
    """Backtest optimizer — find best config parameters."""
    _header()
    print('  Backtest Optimizer\n')
    print('  This will test parameter combinations across all SET stocks.')
    print('  Results are saved to data/optimization_results.csv\n')

    top     = _ask('Show top N results', '10')
    workers = _ask('Parallel workers', '4')
    period  = _ask('Data period (12mo / 2y)', '2y')
    quick   = _ask_yn('Quick mode (fewer combos, faster)?')
    validate= _ask_yn('Walk-forward validation?')

    cmd = ['backtest_optimize.py',
           '--top', top,
           '--workers', workers,
           '--period', period]
    if quick:
        cmd.append('--quick')
    if validate:
        cmd.append('--validate')

    print()
    _run(cmd)


def action_clear_cache():
    """Clear all cached price data."""
    _header()
    print('  Clear Cache\n')

    if _ask_yn('Delete all cached price data? This cannot be undone.'):
        _run(['main.py', '--clear-cache'])
    else:
        print('  Cancelled.')
        input('  Press Enter to return to menu...')


# ── Main menu loop ────────────────────────────────────────────────────────────

MENU = [
    ('End-of-day scan',    'Build watchlist + HTML chart',         action_scan),
    ('Intraday check',     'Scan watchlist for live signals',       action_intraday),
    ('View charts',        'Open today\'s dashboard in browser',    action_view_all),
    ('View single stock',  'Chart for one ticker',                  action_view_stock),
    ('Backtest optimizer', 'Find best config parameters',           action_optimize),
    ('Clear cache',        'Delete all cached price data',          action_clear_cache),
]


def main():
    while True:
        _header()

        for i, (name, desc, _) in enumerate(MENU, 1):
            print(f'  [{i}]  {name:<22}  {desc}')
        print(f'\n  [0]  Exit\n')

        choice = input('  Choice: ').strip()

        if choice == '0':
            print()
            break

        if choice.isdigit() and 1 <= int(choice) <= len(MENU):
            MENU[int(choice) - 1][2]()
        else:
            print('  Invalid choice.')
            input('  Press Enter to continue...')


if __name__ == '__main__':
    main()
