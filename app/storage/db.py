"""
app/storage/db.py — SQLAlchemy engine + session factory
========================================================
Works with both Postgres (DATABASE_URL set) and SQLite (local dev).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

if DATABASE_URL.startswith('sqlite'):
    # SQLite needs check_same_thread=False for FastAPI (multi-threaded)
    _connect_args = {'check_same_thread': False}
else:
    # Postgres (psycopg2): bound every connection so a degraded network can't
    # hang a DB call forever. statement_timeout caps server-side ops; TCP
    # keepalives detect a dead socket within ~60s instead of blocking. Without
    # this, a stalled snapshot commit froze the entire EOD scan mid-run.
    _connect_args = {
        'connect_timeout': 10,
        'keepalives': 1,
        'keepalives_idle': 30,
        'keepalives_interval': 10,
        'keepalives_count': 3,
        'options': '-c statement_timeout=120000',   # 120s per statement
    }

# pool_recycle: discard any pooled connection older than 280s so we never reuse
# one the server has already dropped for being idle (Railway Postgres / pgbouncer).
engine = create_engine(
    DATABASE_URL, connect_args=_connect_args,
    pool_pre_ping=True, pool_recycle=280,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once on app startup."""
    from app.storage.models import Base  # noqa: F401 — import triggers table registration
    Base.metadata.create_all(bind=engine)
