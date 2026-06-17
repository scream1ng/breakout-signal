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
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANSI_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


_LOG_DIR = os.path.join(ROOT, 'data', 'job_logs')


def _run(script: str, *extra_args: str, env_extra: dict | None = None) -> dict:
    """Run a project script as a subprocess, streaming stdout to a log file."""
    cmd = [sys.executable, os.path.join(ROOT, script), *extra_args]
    env = os.environ.copy()
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items() if v is not None})

    job_name = (env_extra or {}).get('ALERT_JOB_NAME')
    log_path = None
    if job_name:
        os.makedirs(_LOG_DIR, exist_ok=True)
        log_path = os.path.join(_LOG_DIR, f'{job_name}.log')

    stdout_lines: list[str] = []
    log_f = open(log_path, 'w', encoding='utf-8') if log_path else None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=ROOT, env=env, bufsize=1,
        )

        def _reader():
            for line in proc.stdout:
                clean = _strip_ansi(line)
                stdout_lines.append(clean)
                if log_f:
                    log_f.write(clean)
                    log_f.flush()

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        proc.wait()          # returns as soon as main process exits
        reader.join(timeout=10)  # drain any buffered output
    finally:
        if log_f:
            log_f.close()

    stdout_tail = ''.join(stdout_lines)[-4000:]
    if proc.returncode != 0:
        raise RuntimeError(
            f'Exit code: {proc.returncode}\n\nSTDOUT:\n{stdout_tail or "(empty)"}'
        )
    return {'return_code': proc.returncode, 'stdout': stdout_tail}


def _job_env(job_context: dict | None, source_fallback: str) -> dict:
    meta = dict(job_context or {})
    return {
        'ALERT_SOURCE': meta.get('source') or source_fallback,
        'ALERT_JOB_NAME': meta.get('job_name'),
        'ALERT_JOB_RUN_ID': meta.get('job_run_id'),
        'ALERT_COMMIT_SHA': os.environ.get('RAILWAY_GIT_COMMIT_SHA', '').strip(),
    }


def run_eod_scan(job_context: dict | None = None) -> dict:
    """EOD watchlist scan — Mon-Fri 16:45 BKK (09:45 UTC)."""
    return _run('main.py', env_extra=_job_env(job_context, 'manual_job'))


def run_intraday_scan(job_context: dict | None = None) -> dict:
    """15-min intraday breakout check — market hours."""
    return _run('intraday.py', env_extra=_job_env(job_context, 'manual_job'))


def run_review_scan(job_context: dict | None = None) -> dict:
    """16:25 BKK fakeout review — checks for failed breaks."""
    return _run('intraday.py', '--review', env_extra=_job_env(job_context, 'manual_job'))


def run_eod_scan_notify(job_context: dict | None = None) -> dict:
    """Scheduled EOD scan with notifications enabled."""
    return _run('main.py', '--discord', env_extra=_job_env(job_context, 'scheduler'))


def run_intraday_scan_notify(job_context: dict | None = None) -> dict:
    """Scheduled intraday scan with notifications enabled."""
    return _run('intraday.py', '--discord', env_extra=_job_env(job_context, 'scheduler'))


def run_review_scan_notify(job_context: dict | None = None) -> dict:
    """Scheduled fakeout review with notifications enabled."""
    return _run('intraday.py', '--review', '--discord', env_extra=_job_env(job_context, 'scheduler'))
