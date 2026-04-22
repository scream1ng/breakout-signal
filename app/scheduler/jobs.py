"""
app/scheduler/jobs.py — Job function definitions
=================================================
Each function is called by the APScheduler runner.
They invoke main.py / intraday.py as subprocesses so the existing
script logic is not disturbed during the restructure.

Return value: dict with optional stats keys:
  stocks_scanned, signals_found, trades_opened, trades_closed
"""

import os
import sys
import json
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run(script: str, *extra_args: str) -> dict:
    """Run a project script as a subprocess; raise on non-zero exit."""
    cmd = [sys.executable, os.path.join(ROOT, script), *extra_args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-800:] or result.stdout[-400:])
    return {}


def run_eod_scan() -> dict:
    """EOD watchlist scan — Mon-Fri 16:45 BKK (09:45 UTC)."""
    return _run('main.py')


def run_intraday_scan() -> dict:
    """15-min intraday breakout check — market hours."""
    return _run('intraday.py')


def run_review_scan() -> dict:
    """16:15 BKK fakeout review — checks for failed breaks."""
    return _run('intraday.py', '--review')
