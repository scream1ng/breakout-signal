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
TRADE_MODE: str = os.getenv('TRADE_MODE', 'paper').lower()   # 'paper' | 'live'
PORT: int = int(os.getenv('PORT', '8080'))

def _default_sqlite_url() -> str:
    # Railway may boot without a Postgres plugin attached. Use a writable
    # ephemeral path instead of /app/data, which may not exist at startup.
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID'):
        sqlite_dir = os.path.join(os.getenv('TMPDIR', '/tmp'), 'breakout-signal')
    else:
        sqlite_dir = os.path.join(_ROOT, 'data')
    os.makedirs(sqlite_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(sqlite_dir, 'app.db')}"


# Database: prefer Postgres (Railway) → fallback to SQLite
DATABASE_URL: str = os.getenv('DATABASE_URL', _default_sqlite_url())

# Notification channels
DISCORD_WEBHOOK: str       = os.getenv('DISCORD_WEBHOOK', '').strip()
LINE_TOKEN: str            = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
LINE_MODE: str             = os.getenv('LINE_MODE', 'push').strip().lower()
LINE_TARGETS: list[str]    = [
    t.strip()
    for t in os.getenv('LINE_TO', '').split(',')
    if t.strip()
]
for _key in ('LINE_USER_ID', 'LINE_GROUP_ID', 'LINE_ROOM_ID'):
    _v = os.getenv(_key, '').strip()
    if _v and _v not in LINE_TARGETS:
        LINE_TARGETS.append(_v)

# Public URL used in notification links
APP_BASE_URL: str = (
    os.getenv('APP_BASE_URL', '').rstrip('/')
    or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()}"
        if os.getenv('RAILWAY_PUBLIC_DOMAIN') else '')
    or 'http://localhost:8080'
)
