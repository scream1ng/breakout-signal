"""
app/scheduler/runner.py — APScheduler setup with job-run tracking
==================================================================
Every job is wrapped so a JobRun row is written to the DB before
and after each execution. The web dashboard reads this table to
show live status, last run, duration, and errors.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from app.storage.db import SessionLocal
from app.storage.models import JobRun

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _as_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for safe arithmetic."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
    return _scheduler


def _tracked(job_name: str, fn: Callable, *args, **kwargs) -> None:
    """Wrap a job function: create JobRun before, update it after."""
    db = SessionLocal()
    run = JobRun(
        job_name=job_name,
        status='running',
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    result: dict = {}
    try:
        result = fn(*args, **kwargs) or {}
        run.status = 'completed'
        started_utc = _as_utc(run.started_at)
        logger.info('Job %s completed in %.1fs', job_name,
                    (datetime.now(timezone.utc) - started_utc).total_seconds())
    except Exception as exc:
        run.status = 'failed'
        run.error  = str(exc)[:800]
        logger.exception('Job %s failed', job_name)
        # Notify ops via Discord on job failure (non-blocking)
        try:
            from app.notifications.discord import send_job_failure
            send_job_failure(job_name, str(exc))
        except Exception:
            pass
    finally:
        run.finished_at = datetime.now(timezone.utc)
        run.duration_s  = (_as_utc(run.finished_at) - _as_utc(run.started_at)).total_seconds()
        for key in ('stocks_scanned', 'signals_found', 'trades_opened', 'trades_closed'):
            if key in result:
                setattr(run, key, result[key])
        run.result_json = json.dumps(result)
        db.add(run)
        db.commit()
        db.close()


def register_jobs() -> None:
    """Register all production scheduled jobs with APScheduler."""
    from app.scheduler.jobs import run_eod_scan, run_intraday_scan, run_review_scan

    scheduler = get_scheduler()

    # ── EOD scan: Mon-Fri 09:45 UTC = 16:45 BKK ─────────────────────────────
    scheduler.add_job(
        _tracked, 'cron',
        args=['eod_scan', run_eod_scan],
        day_of_week='mon-fri', hour=9, minute=45,
        id='eod_scan', replace_existing=True,
    )

    # ── Intraday scans: 15-min cadence during market hours ───────────────────
    _intraday_bkk = [
        '10:30', '10:45', '11:00', '11:15', '11:30', '11:45',
        '12:00', '12:15', '12:30',
        '14:30', '14:45', '15:00', '15:15', '15:30', '15:45', '16:00',
    ]
    for i, t_bkk in enumerate(_intraday_bkk):
        h, m = map(int, t_bkk.split(':'))
        h_utc = (h - 7) % 24
        scheduler.add_job(
            _tracked, 'cron',
            args=['intraday_scan', run_intraday_scan],
            day_of_week='mon-fri', hour=h_utc, minute=m,
            id=f'intraday_{i}', replace_existing=True,
        )

    # ── Fakeout review: Mon-Fri 09:15 UTC = 16:15 BKK ───────────────────────
    scheduler.add_job(
        _tracked, 'cron',
        args=['review_scan', run_review_scan],
        day_of_week='mon-fri', hour=9, minute=15,
        id='review_scan', replace_existing=True,
    )

    logger.info('Registered %d jobs', len(scheduler.get_jobs()))
