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


def _norm_ticker(t: str) -> str:
    """DELTA / set:delta / DELTA.BK → DELTA.BK (matches stored PK)."""
    t = str(t or '').upper().replace('SET:', '').strip()
    if not t:
        return t
    if t.startswith('^') or t.endswith('.BK') or t.endswith('.AX'):
        return t
    return t + '.BK'


def load_chart(ticker: str) -> dict | None:
    """Return the stored get_chart_data() dict for *ticker*, or None."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import ChartData
        init_db()
        db = SessionLocal()
        try:
            row = db.query(ChartData).filter_by(ticker=_norm_ticker(ticker)).first()
            if row:
                return json.loads(row.data_json)
        finally:
            db.close()
    except Exception:
        pass
    return None


def save_chart(ticker: str, scan_date: str, data: dict) -> bool:
    """Upsert one ticker's chart payload. Returns True on success."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import ChartData
        init_db()
        db = SessionLocal()
        try:
            tk = _norm_ticker(ticker)
            row = db.query(ChartData).filter_by(ticker=tk).first()
            payload = json.dumps(data, ensure_ascii=False)
            if row:
                row.data_json = payload
                row.scan_date = scan_date
                row.updated_at = datetime.now(timezone.utc)
            else:
                db.add(ChartData(
                    ticker=tk, scan_date=scan_date, data_json=payload,
                    updated_at=datetime.now(timezone.utc),
                ))
            db.commit()
            return True
        finally:
            db.close()
    except Exception:
        pass
    return False


def prune_charts(keep_tickers) -> int:
    """Delete ChartData rows whose ticker is not in *keep_tickers*. Returns count."""
    try:
        from app.storage.db import SessionLocal, init_db
        from app.storage.models import ChartData
        init_db()
        keep = {_norm_ticker(t) for t in keep_tickers}
        db = SessionLocal()
        try:
            n = 0
            for row in db.query(ChartData).all():
                if row.ticker not in keep:
                    db.delete(row)
                    n += 1
            db.commit()
            return n
        finally:
            db.close()
    except Exception:
        pass
    return 0


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
