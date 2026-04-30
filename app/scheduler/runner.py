"""
app/scheduler/runner.py — APScheduler setup with job-run tracking
==================================================================
Every job is wrapped so a JobRun row is written to the DB before
and after each execution. The web dashboard reads this table to
show live status, last run, duration, and errors.

Duplicate-run protection: atomic INSERT ON CONFLICT into job_locks table.
Two scheduler instances (e.g. Railway + local) cannot run the same job
simultaneously — the second instance acquires no lock and exits early.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.storage.db import SessionLocal
from app.storage.models import JobRun

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _as_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for safe arithmetic."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_lock_table(db) -> None:
    """Create job_locks table if it doesn't exist (idempotent)."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS job_locks (
                job_name  TEXT        PRIMARY KEY,
                locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.commit()
    except Exception:
        db.rollback()


def _acquire_lock(db, job_name: str) -> bool:
    """
    Atomically claim a job slot via INSERT ON CONFLICT.
    Returns True if this instance acquired the lock.
    Stale locks older than 10 min are cleaned up first.
    """
    try:
        db.execute(
            text("DELETE FROM job_locks WHERE locked_at < NOW() - INTERVAL '10 minutes'")
        )
        result = db.execute(
            text(
                "INSERT INTO job_locks (job_name) VALUES (:name)"
                " ON CONFLICT DO NOTHING RETURNING job_name"
            ),
            {'name': job_name},
        )
        db.commit()
        return result.fetchone() is not None
    except Exception as exc:
        logger.warning('Lock table unavailable (%s) — running without dedup', exc)
        try:
            db.rollback()
        except Exception:
            pass
        return True  # SQLite fallback or table not ready — allow run


def _release_lock(db, job_name: str) -> None:
    try:
        db.execute(text("DELETE FROM job_locks WHERE job_name = :name"), {'name': job_name})
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
    return _scheduler


def _tracked(job_name: str, fn: Callable, *args, **kwargs) -> None:
    """Wrap a job function: create JobRun before, update it after."""
    db = SessionLocal()
    _ensure_lock_table(db)

    if not _acquire_lock(db, job_name):
        logger.warning('Job %s skipped — duplicate (lock held by other instance)', job_name)
        db.close()
        return

    try:
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
    finally:
        _release_lock(db, job_name)
        db.close()


def register_jobs() -> None:
    """Register all production scheduled jobs with APScheduler."""
    from app.scheduler.jobs import (
        run_eod_scan_notify,
        run_intraday_scan_notify,
        run_review_scan_notify,
    )

    scheduler = get_scheduler()

    # ── EOD scan: Mon-Fri 09:45 UTC = 16:45 BKK ─────────────────────────────
    scheduler.add_job(
        _tracked, 'cron',
        args=['eod_scan', run_eod_scan_notify],
        day_of_week='mon-fri', hour=9, minute=45,
        id='eod_scan', replace_existing=True,
    )

    # ── Intraday scans: every 15 min 10:15–12:30 + 14:00–16:15 BKK ────────────
    _intraday_bkk = [
        f'{h:02d}:{m:02d}'
        for h in range(10, 17)
        for m in (0, 15, 30, 45)
        if (10 * 60 + 15) <= (h * 60 + m) <= (12 * 60 + 30)
        or (14 * 60 + 0)  <= (h * 60 + m) <= (16 * 60 + 15)
    ]
    for i, t_bkk in enumerate(_intraday_bkk):
        h, m = map(int, t_bkk.split(':'))
        h_utc = h - 7
        scheduler.add_job(
            _tracked, 'cron',
            args=['intraday_scan', run_intraday_scan_notify],
            day_of_week='mon-fri', hour=h_utc, minute=m,
            id=f'intraday_{i}', replace_existing=True,
        )

    # ── Fakeout review: Mon-Fri 09:25 UTC = 16:25 BKK ───────────────────────
    scheduler.add_job(
        _tracked, 'cron',
        args=['review_scan', run_review_scan_notify],
        day_of_week='mon-fri', hour=9, minute=25,
        id='review_scan', replace_existing=True,
    )

    logger.info('Registered %d jobs', len(scheduler.get_jobs()))
