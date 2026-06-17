"""
app/api/system.py — GET /api/system
=====================================
Returns scheduler status, recent job run history, and API health.
Powers the "Dashboard" page on the web frontend.
"""

import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import DISCORD_WEBHOOK, OPS_API_TOKEN
from app.notifications.discord import send_test_alert as send_discord_test_alert
from app.storage.db import get_db
from app.storage.models import JobRun, NotificationSend
from app.scheduler.runner import get_scheduler

_STALE_THRESHOLD = timedelta(minutes=15)


def _mark_stale(row: dict) -> dict:
    """Return row dict with status='stale' if stuck in 'running' > 15 min."""
    if row.get('status') == 'running' and row.get('started_at'):
        try:
            started = datetime.fromisoformat(row['started_at'])
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - started > _STALE_THRESHOLD:
                row = dict(row, status='stale')
        except Exception:
            pass
    return row

router = APIRouter()


def _require_ops_access(x_ops_token: str | None = Header(default=None)) -> None:
    if OPS_API_TOKEN and x_ops_token != OPS_API_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid or missing x-ops-token')


@router.get('/system')
def get_system_status(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    scheduler = get_scheduler()

    # Next scheduled run per unique job id
    next_runs: dict[str, str | None] = {}
    for job in scheduler.get_jobs():
        # Group intraday_N jobs under a single key
        key = job.id if not job.id.startswith('intraday_') else 'intraday_scan'
        nrt = job.next_run_time
        candidate = nrt.isoformat() if nrt else None
        if key not in next_runs or (candidate and (not next_runs[key] or candidate < next_runs[key])):
            next_runs[key] = candidate

    # Recent job runs from DB
    runs = (
        db.query(JobRun)
        .order_by(JobRun.started_at.desc())
        .limit(limit)
        .all()
    )

    # Last run per job_name for summary
    last_by_job: dict[str, dict] = {}
    for run in runs:
        if run.job_name not in last_by_job:
            last_by_job[run.job_name] = _mark_stale(run.to_dict())

    notifications = (
        db.query(NotificationSend)
        .order_by(NotificationSend.created_at.desc())
        .limit(min(limit, 20))
        .all()
    )

    return {
        'scheduler_running': scheduler.running,
        'next_runs':         next_runs,
        'last_runs':         last_by_job,
        'recent_history':    [_mark_stale(r.to_dict()) for r in runs],
        'recent_notifications': [n.to_dict() for n in notifications],
    }


# ── Manually trigger a job ────────────────────────────────────────────────────
_JOB_MAP: dict | None = None


def _get_job_map() -> dict:
    global _JOB_MAP
    if _JOB_MAP is None:
        from app.scheduler.jobs import run_eod_scan, run_intraday_scan, run_review_scan
        _JOB_MAP = {
            'eod_scan':      run_eod_scan,
            'intraday_scan': run_intraday_scan,
            'review_scan':   run_review_scan,
        }
    return _JOB_MAP


@router.post('/jobs/run/{job_name}')
def trigger_job(
    job_name: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_ops_access),
):
    """Trigger a job immediately in the background. Returns straight away."""
    job_map = _get_job_map()
    if job_name not in job_map:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown job '{job_name}'. Valid: {list(job_map)}",
        )
    from app.scheduler.runner import _tracked
    background_tasks.add_task(_tracked, job_name, job_map[job_name], trigger_source='api_manual')
    return {'status': 'triggered', 'job': job_name}


@router.get('/jobs/log/{job_name}')
def get_job_log(job_name: str, offset: int = Query(default=0)):
    """Return log lines from the running/last job subprocess output."""
    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_path = os.path.join(_ROOT, 'data', 'job_logs', f'{job_name}.log')
    if not os.path.exists(log_path):
        return {'lines': [], 'total': 0, 'offset': 0}
    try:
        with open(log_path, encoding='utf-8') as f:
            all_lines = f.readlines()
        return {
            'lines': [ln.rstrip('\n') for ln in all_lines[offset:]],
            'total': len(all_lines),
            'offset': offset,
        }
    except Exception:
        return {'lines': [], 'total': 0, 'offset': 0}


@router.post('/notify/test/{channel}')
def trigger_notification_test(channel: str, _: None = Depends(_require_ops_access)):
    channel_name = channel.strip().lower()

    if channel_name != 'discord':
        raise HTTPException(status_code=404, detail="Unknown channel. Valid: ['discord']")
    if not DISCORD_WEBHOOK:
        raise HTTPException(status_code=400, detail='DISCORD_WEBHOOK is not configured')

    ok = send_discord_test_alert()
    if not ok:
        raise HTTPException(status_code=502, detail='Discord test notification failed')

    return {'status': 'sent', 'channel': channel_name}
