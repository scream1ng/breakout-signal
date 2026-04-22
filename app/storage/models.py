"""
app/storage/models.py — SQLAlchemy ORM models
==============================================
JobRun  — one row per scheduled job execution.
          Provides the visibility layer shown on the web dashboard.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
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
        }
