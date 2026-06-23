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
import os
from datetime import datetime, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.storage.db import SessionLocal
from app.storage.models import JobRun
from app.scheduler.windows import EOD_BKK_SLOT, INTRADAY_BKK_SLOTS, REVIEW_BKK_SLOTS

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
        claimed = result.fetchone() is not None
        db.commit()
        return claimed
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


def sweep_stale_runs(max_age_s: int = 1800) -> int:
    """Mark orphaned 'running' JobRuns (older than max_age_s) as 'failed'.

    A run is orphaned when its process hung or was killed mid-scan (e.g. a
    Railway redeploy terminating the web process). Without this, the row stays
    'running' forever and the dashboard/chart appears stuck. Returns rows fixed.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(JobRun).filter(JobRun.status == 'running').all()
        fixed = 0
        for r in rows:
            age = (now - _as_utc(r.started_at)).total_seconds()
            if age > max_age_s:
                r.status      = 'failed'
                r.error       = f'Orphaned — still running after {int(age)}s; marked failed on sweep.'
                r.finished_at = now
                r.duration_s  = age
                db.add(r)
                fixed += 1
        if fixed:
            # Release locks for swept jobs so the next run isn't blocked until
            # the 10-min stale-lock cleanup; the owning process is already gone.
            for name in {r.job_name for r in rows if r.status == 'failed'}:
                try:
                    db.execute(text("DELETE FROM job_locks WHERE job_name = :n"), {'n': name})
                except Exception:
                    pass
            db.commit()
        return fixed
    except Exception as exc:
        logger.warning('Stale-run sweep failed: %s', exc)
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()


_RETENTION_DAYS = int(os.environ.get('JOBRUN_RETENTION_DAYS', '30'))


def _prune_old_rows(db) -> None:
    """Delete job_runs / notification_sends older than retention window.

    Postgres-only (uses NOW()/INTERVAL like the lock table). Runs once a day
    off the EOD job so these append-only tables don't grow without bound and
    bloat the Railway Postgres volume. Silently no-ops on SQLite / failure.
    """
    for table, ts_col in (('job_runs', 'started_at'), ('notification_sends', 'created_at')):
        try:
            db.execute(text(
                f"DELETE FROM {table} "
                f"WHERE {ts_col} < NOW() - INTERVAL '{_RETENTION_DAYS} days'"
            ))
            db.commit()
        except Exception:
            db.rollback()


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
    return _scheduler


def _tracked(job_name: str, fn: Callable, *args, trigger_source: str = 'scheduler', **kwargs) -> None:
    """Wrap a job function: create JobRun before, update it after.

    DB sessions are short-lived and never held across fn(). A scan runs
    ~14-16 min; a connection checked out for that whole span gets dropped by
    the server while idle, so the final 'completed' commit would fail and the
    row would stay 'running' even though the work finished. Insert with one
    session, run the job holding none, then write the result with a fresh one.
    """
    # ── 1. Acquire lock + insert the 'running' row (short session) ────────────
    db = SessionLocal()
    _ensure_lock_table(db)
    if not _acquire_lock(db, job_name):
        logger.warning('Job %s skipped — duplicate (lock held by other instance)', job_name)
        db.close()
        return

    started = datetime.now(timezone.utc)
    run_id = None
    try:
        run = JobRun(job_name=job_name, status='running', started_at=started)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    except Exception:
        logger.exception('Job %s — failed to create JobRun row', job_name)
    finally:
        db.close()

    # ── 2. Run the job WITHOUT holding a DB connection ────────────────────────
    status = 'completed'
    error = None
    result: dict = {}
    try:
        result = fn(
            *args,
            job_context={'source': trigger_source, 'job_name': job_name, 'job_run_id': run_id},
            **kwargs,
        ) or {}
        logger.info('Job %s completed in %.1fs', job_name,
                    (datetime.now(timezone.utc) - started).total_seconds())
    except Exception as exc:
        status = 'failed'
        error = str(exc)[:800]
        logger.exception('Job %s failed', job_name)
        try:
            from app.notifications.discord import send_job_failure
            send_job_failure(job_name, str(exc))
        except Exception:
            pass

    # ── 3. Persist final status + release lock (fresh session) ────────────────
    finished = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        run = db.get(JobRun, run_id) if run_id is not None else None
        if run is not None:
            run.status      = status
            run.error       = error
            run.finished_at = finished
            run.duration_s  = (finished - started).total_seconds()
            for key in ('stocks_scanned', 'signals_found', 'trades_opened', 'trades_closed'):
                if key in result:
                    setattr(run, key, result[key])
            run.result_json = json.dumps(result)
            db.commit()
        if job_name == 'eod_scan':
            _prune_old_rows(db)
    except Exception:
        logger.exception('Job %s — failed to persist final status', job_name)
        try:
            db.rollback()
        except Exception:
            pass
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
    eod_hour_bkk, eod_minute_bkk = map(int, EOD_BKK_SLOT.split(':'))
    scheduler.add_job(
        _tracked, 'cron',
        args=['eod_scan', run_eod_scan_notify],
        day_of_week='mon-fri', hour=(eod_hour_bkk - 7) % 24, minute=eod_minute_bkk,
        id='eod_scan', replace_existing=True,
    )

    # ── Intraday scans: every 15 min 10:30–12:30 + 14:00–16:15 BKK ────────────
    for i, t_bkk in enumerate(INTRADAY_BKK_SLOTS):
        h, m = map(int, t_bkk.split(':'))
        h_utc = (h - 7) % 24
        scheduler.add_job(
            _tracked, 'cron',
            args=['intraday_scan', run_intraday_scan_notify],
            day_of_week='mon-fri', hour=h_utc, minute=m,
            id=f'intraday_{i}', replace_existing=True,
        )

    # ── Fakeout review: Mon-Fri 09:25 UTC = 16:25 BKK ───────────────────────
    for i, t_bkk in enumerate(REVIEW_BKK_SLOTS):
        h, m = map(int, t_bkk.split(':'))
        scheduler.add_job(
            _tracked, 'cron',
            args=['review_scan', run_review_scan_notify],
            day_of_week='mon-fri', hour=(h - 7) % 24, minute=m,
            id='review_scan' if i == 0 else f'review_scan_{i}', replace_existing=True,
        )

    logger.info('Registered %d jobs', len(scheduler.get_jobs()))
