"""
app/storage/state.py — DB-backed key/value store for daily state.

Wraps DailyState table. Falls back silently to None when DB unavailable
so callers can fall back to JSON files (local dev without DATABASE_URL).
"""

from __future__ import annotations
import json
from datetime import datetime, timezone


def load_state(key: str) -> dict | list | None:
    """Return parsed JSON for *key*, or None if not found / DB unavailable."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import DailyState
        init_db()
        db = SessionLocal()
        try:
            row = db.query(DailyState).filter_by(state_key=key).first()
            if row:
                return json.loads(row.state_json)
        finally:
            db.close()
    except Exception:
        pass
    return None


def save_state(key: str, data: dict | list) -> bool:
    """Upsert *data* under *key*. Returns True on success."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import DailyState
        init_db()
        db = SessionLocal()
        try:
            row = db.query(DailyState).filter_by(state_key=key).first()
            payload = json.dumps(data, ensure_ascii=False)
            if row:
                row.state_json = payload
                row.updated_at = datetime.now(timezone.utc)
            else:
                db.add(DailyState(
                    state_key=key,
                    state_json=payload,
                    updated_at=datetime.now(timezone.utc),
                ))
            db.commit()
            return True
        finally:
            db.close()
    except Exception:
        pass
    return False
