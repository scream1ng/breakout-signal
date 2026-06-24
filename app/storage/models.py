"""
app/storage/models.py — SQLAlchemy ORM models
==============================================
JobRun  — one row per scheduled job execution.
          Provides the visibility layer shown on the web dashboard.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Date, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


def _utc_iso(dt: datetime | None) -> str | None:
    """Serialize DB timestamps as explicit UTC so browsers do not assume local time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


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
            'started_at':     _utc_iso(self.started_at),
            'finished_at':    _utc_iso(self.finished_at),
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
            'created_at': _utc_iso(self.created_at),
            'n_stocks':   self.n_stocks,
            'n_signals':  self.n_signals,
            'n_watching': self.n_watching,
        }


# ── ChartData — one small row per ticker with its chart-render payload ────────
class ChartData(Base):
    """Per-ticker chart payload (get_chart_data() dict) for /api/chart/{ticker}.

    Replaces the old multi-MB DailyState 'chart_html' blob. EOD scan writes one
    small row per signal/watchlist ticker; tickers not stored are rebuilt
    on demand (candles + MAs) from the OHLCV cache.
    """
    __tablename__ = 'chart_data'

    ticker     = Column(String(20), primary_key=True)   # normalized, e.g. DELTA.BK
    scan_date  = Column(String(10), nullable=True, index=True)   # YYYY-MM-DD
    data_json  = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc))


# ── DailyState — key/value store for ephemeral daily data ────────────────────
class DailyState(Base):
    """Persists daily data that must survive Railway redeploys.

    Keys used:
      'watchlist'              — EOD watchlist (written by main.py, read by intraday.py)
      'alert_state:{YYYY-MM-DD}' — intraday alert dedup + fakeout log for one day
    """
    __tablename__ = 'daily_state'

    state_key  = Column(String(80), primary_key=True)
    state_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc))


class NotificationSend(Base):
    __tablename__ = 'notification_sends'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    channel    = Column(String(20), nullable=False, index=True)
    target     = Column(String(120), nullable=False)
    header     = Column(String(120), nullable=False)
    source     = Column(String(40), nullable=True, index=True)
    job_name   = Column(String(60), nullable=True, index=True)
    job_run_id = Column(Integer, nullable=True, index=True)
    commit_sha = Column(String(40), nullable=True)
    status     = Column(String(20), nullable=False, index=True)
    error      = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'channel':    self.channel,
            'target':     self.target,
            'header':     self.header,
            'source':     self.source,
            'job_name':   self.job_name,
            'job_run_id': self.job_run_id,
            'commit_sha': self.commit_sha,
            'status':     self.status,
            'error':      self.error,
            'created_at': _utc_iso(self.created_at),
        }
