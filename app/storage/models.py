"""
app/storage/models.py — SQLAlchemy ORM models
==============================================
JobRun  — one row per scheduled job execution.
          Provides the visibility layer shown on the web dashboard.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Date, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class JobRun(Base):
    __tablename__ = 'job_runs'

    id             = Column(Integer, primary_key=True, autoincrement=True)
    job_name       = Column(String(60), nullable=False, index=True)
    status         = Column(String(20), nullable=False)   # running | completed | failed
    started_at     = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at    = Column(DateTime, nullable=True)
    duration_s     = Column(Float,    nullable=True)

    # Optional stats populated by each job
    stocks_scanned = Column(Integer, nullable=True)
    signals_found  = Column(Integer, nullable=True)
    trades_opened  = Column(Integer, nullable=True)
    trades_closed  = Column(Integer, nullable=True)

    error          = Column(Text, nullable=True)   # last 500 chars of stderr / exception
    result_json    = Column(Text, nullable=True)   # full JSON dict returned by job fn

    def to_dict(self) -> dict:
        return {
            'id':             self.id,
            'job_name':       self.job_name,
            'status':         self.status,
            'started_at':     self.started_at.isoformat() if self.started_at else None,
            'finished_at':    self.finished_at.isoformat() if self.finished_at else None,
            'duration_s':     self.duration_s,
            'stocks_scanned': self.stocks_scanned,
            'signals_found':  self.signals_found,
            'trades_opened':  self.trades_opened,
            'trades_closed':  self.trades_closed,
            'error':          self.error,
            'result_json':    self.result_json,
        }


# ── ScanSnapshot — one row per EOD scan run ───────────────────────────────────
class ScanSnapshot(Base):
    """Persists full EOD scan output so the web dashboard can serve it via API."""
    __tablename__ = 'scan_snapshots'
    __table_args__ = (UniqueConstraint('scan_date', name='uq_scan_snapshots_date'),)

    id         = Column(Integer, primary_key=True, autoincrement=True)
    scan_date  = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD
    created_at = Column(DateTime,   nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    n_stocks   = Column(Integer, nullable=True)
    n_signals  = Column(Integer, nullable=True)
    n_watching = Column(Integer, nullable=True)
    # Full JSON payload — backtest_rows, watchlist, signals, sector, overall_bt
    data_json  = Column(Text,    nullable=False)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'scan_date':  self.scan_date,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'n_stocks':   self.n_stocks,
            'n_signals':  self.n_signals,
            'n_watching': self.n_watching,
        }
