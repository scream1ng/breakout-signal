"""
app/config.py — Centralised config loader
==========================================
Reads .env once (via python-dotenv), then exposes typed settings.
All modules import from here instead of re-reading os.environ.
"""

import os
from dotenv import load_dotenv

# Load .env from project root (harmless if missing in prod)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, '.env'), override=False)

# ── Trade settings (re-export from config.py for convenience) ────────────────
try:
    import sys
    sys.path.insert(0, _ROOT)
    from config import CFG as TRADE_CFG
except ImportError:
    TRADE_CFG: dict = {}

# ── App settings ──────────────────────────────────────────────────────────────
PORT: int = int(os.getenv('PORT', '8080'))


def is_railway_runtime() -> bool:
    return bool(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID'))

def _default_sqlite_url() -> str:
    # Railway may boot without a Postgres plugin attached. Use a writable
    # ephemeral path instead of /app/data, which may not exist at startup.
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID'):
        sqlite_dir = os.path.join(os.getenv('TMPDIR', '/tmp'), 'breakout-signal')
    else:
        sqlite_dir = os.path.join(_ROOT, 'data')
    os.makedirs(sqlite_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(sqlite_dir, 'app.db')}"


# Database: require shared DB on Railway, allow SQLite fallback locally.
_database_url = os.getenv('DATABASE_URL', '').strip()
if is_railway_runtime():
    if not _database_url:
        raise RuntimeError('DATABASE_URL must be configured on Railway; SQLite fallback is disabled in production.')
    if _database_url.startswith('sqlite'):
        raise RuntimeError('DATABASE_URL must point to Postgres on Railway; SQLite is not supported in production.')
DATABASE_URL: str = _database_url or _default_sqlite_url()

# Notification channels
DISCORD_WEBHOOK: str = os.getenv('DISCORD_WEBHOOK', '').strip()
OPS_API_TOKEN: str = os.getenv('OPS_API_TOKEN', '').strip()

# Public URL used in notification links
APP_BASE_URL: str = (
    os.getenv('APP_BASE_URL', '').rstrip('/')
    or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()}"
        if os.getenv('RAILWAY_PUBLIC_DOMAIN') else '')
    or 'http://localhost:8080'
)
