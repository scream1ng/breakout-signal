"""
app/api/system.py — GET /api/system
=====================================
Returns scheduler status, recent job run history, and API health.
Powers the "Dashboard" page on the web frontend.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.storage.db import get_db
from app.storage.models import JobRun
from app.scheduler.runner import get_scheduler

router = APIRouter()


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
            last_by_job[run.job_name] = run.to_dict()

    return {
        'scheduler_running': scheduler.running,
        'next_runs':         next_runs,
        'last_runs':         last_by_job,
        'recent_history':    [r.to_dict() for r in runs],
    }
