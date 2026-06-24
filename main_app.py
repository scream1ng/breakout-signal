"""
main_app.py — FastAPI entry point
==================================
Run locally:   uvicorn main_app:app --reload --port 8080
Deploy:        Procfile → web: uvicorn main_app:app --host 0.0.0.0 --port $PORT

Serves:
  /             → frontend/index.html  (web dashboard SPA)
  /static/      → frontend/static/
  /chart        → frontend/chart.html (or DB-persisted chart_html)
  /api/system   → scheduler status + job history
  /api/signals  → watchlist + today's intraday breaks
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.storage.db import init_db
from app.scheduler.runner import get_scheduler, register_jobs
from app.api import system, portfolio, signals, trades, scan

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
)
logger = logging.getLogger(__name__)

ROOT         = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, 'frontend')
STATIC_DIR   = os.path.join(FRONTEND_DIR, 'static')

# Ensure required directories exist
os.makedirs(STATIC_DIR, exist_ok=True)


def _frontend_asset_version() -> str:
    commit_sha = os.getenv('RAILWAY_GIT_COMMIT_SHA', '').strip()
    if commit_sha:
        return commit_sha[:12]

    candidates = [
        os.path.join(FRONTEND_DIR, 'index.html'),
        os.path.join(STATIC_DIR, 'app.js'),
        os.path.join(STATIC_DIR, 'style.css'),
        os.path.join(STATIC_DIR, 'bs-data.jsx'),
        os.path.join(STATIC_DIR, 'bs-views.jsx'),
        os.path.join(STATIC_DIR, 'bs-app.jsx'),
    ]
    latest_mtime = 0
    for path in candidates:
        if os.path.exists(path):
            latest_mtime = max(latest_mtime, int(os.path.getmtime(path)))
    return str(latest_mtime or 1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info('Initialising database …')
    init_db()

    # Any run still 'running' at boot was orphaned by the previous process
    # (redeploy/crash mid-scan). Scans take 14-16 min, so a 5-min cutoff clears
    # leftovers fast without touching a genuinely active run.
    from app.scheduler.runner import sweep_stale_runs
    swept = sweep_stale_runs(max_age_s=300)
    if swept:
        logger.info('Swept %d orphaned running job(s) → failed', swept)

    logger.info('Starting scheduler …')
    scheduler = get_scheduler()
    register_jobs()
    scheduler.start()
    logger.info('Scheduler started — %d jobs registered', len(scheduler.get_jobs()))

    yield   # ← app is running

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info('Shutting down scheduler …')
    scheduler.shutdown(wait=False)


app = FastAPI(
    title='Breakout Signal',
    lifespan=lifespan,
    docs_url='/api/docs',
    redoc_url=None,
    openapi_url='/api/openapi.json',
)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(system.router,    prefix='/api', tags=['System'])
app.include_router(portfolio.router, prefix='/api', tags=['Portfolio'])
app.include_router(signals.router,   prefix='/api', tags=['Signals'])
app.include_router(trades.router,    prefix='/api', tags=['Trades'])
app.include_router(scan.router,      prefix='/api', tags=['Scan'])

# ── Static file mounts ────────────────────────────────────────────────────────
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


# ── Chart route (legacy) ─────────────────────────────────────────────────────
# Charts now render natively in the SPA via /api/chart/{ticker}. Keep this path
# as a redirect for old bookmarks/links — optionally honoring ?ticker=.
@app.get('/chart', include_in_schema=False)
def serve_chart(ticker: str = ''):
    target = '/'
    if ticker:
        target = f'/?tab=chart&ticker={ticker}'
    return RedirectResponse(url=target)


# ── SPA catch-all ─────────────────────────────────────────────────────────────
@app.get('/', include_in_schema=False)
@app.get('/{full_path:path}', include_in_schema=False)
def spa(full_path: str = ''):
    # Let /docs and /api and /static pass through to their mounts first.
    # This catch-all only fires for unknown paths → serve the SPA shell.
    index = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index):
        with open(index, encoding='utf-8') as f:
            html = f.read()

        asset_version = _frontend_asset_version()
        for fname in ('style.css', 'app.js', 'bs-data.jsx', 'bs-views.jsx', 'bs-app.jsx'):
            html = html.replace(f'/static/{fname}', f'/static/{fname}?v={asset_version}')
        return HTMLResponse(html)
    return {'detail': 'Frontend not found — run from project root'}
