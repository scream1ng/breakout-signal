"""
app/storage/db.py — SQLAlchemy engine + session factory
========================================================
Works with both Postgres (DATABASE_URL set) and SQLite (local dev).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# SQLite needs check_same_thread=False for FastAPI (multi-threaded)
_connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
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
