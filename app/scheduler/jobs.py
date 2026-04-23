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
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANSI_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def _run(script: str, *extra_args: str) -> dict:
    """Run a project script as a subprocess; raise on non-zero exit."""
    cmd = [sys.executable, os.path.join(ROOT, script), *extra_args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    stdout_tail = _strip_ansi((result.stdout or ''))[-4000:]
    stderr_tail = _strip_ansi((result.stderr or ''))[-4000:]
    if result.returncode != 0:
        detail = (
            f'Exit code: {result.returncode}\n\n'
            f'STDERR:\n{stderr_tail[-2000:] or "(empty)"}\n\n'
            f'STDOUT:\n{stdout_tail[-2000:] or "(empty)"}'
        )
        raise RuntimeError(detail)
    return {
        'return_code': result.returncode,
        'stdout': stdout_tail,
        'stderr': stderr_tail,
    }


def run_eod_scan() -> dict:
    """EOD watchlist scan — Mon-Fri 16:45 BKK (09:45 UTC)."""
    return _run('main.py')


def run_intraday_scan() -> dict:
    """15-min intraday breakout check — market hours."""
    return _run('intraday.py')


def run_review_scan() -> dict:
    """16:15 BKK fakeout review — checks for failed breaks."""
    return _run('intraday.py', '--review')


def run_eod_scan_notify() -> dict:
    """Scheduled EOD scan with notifications enabled."""
    return _run('main.py', '--discord')


def run_intraday_scan_notify() -> dict:
    """Scheduled intraday scan with notifications enabled."""
    return _run('intraday.py', '--discord')


def run_review_scan_notify() -> dict:
    """Scheduled fakeout review with notifications enabled."""
    return _run('intraday.py', '--review', '--discord')
