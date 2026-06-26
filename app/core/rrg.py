"""
rrg.py — Relative Rotation Graph universe for the Screener
==========================================================
Computes JdK-style RS-Ratio + RS-Momentum (both centered at 100) for every
pre-screened SET stock vs the benchmark, rolls members up into sectors, and
returns a payload matching the frontend's RRG universe shape.

  calc_rrg(close, bench)            -> (rs_ratio, rs_momentum, ratio_series)
  build_screener(tv_stocks, bench)  -> {sectors, stocks, total, generated_at}

No network: reads only the OHLCV disk cache that the EOD scan already populated.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.core.data import load_ticker

# Smoothing windows (daily bars). 50 ≈ a quarter for the strength baseline,
# 15 for the shorter momentum-of-strength leg.
WR = 50
WM = 15
MIN_BARS = WR + WM + 5   # need enough history for both rolling means

# Plot bounds — keep dots inside the rotation map (matches the frontend axes).
PLOT_LO, PLOT_HI = 91.5, 108.5


def _clamp_plot(v: float) -> float:
    return max(PLOT_LO, min(PLOT_HI, v))


def calc_rrg(close: np.ndarray, bench: np.ndarray,
             wr: int = WR, wm: int = WM) -> tuple[float, float, np.ndarray]:
    """Return (RS-Ratio, RS-Momentum, full RS-Ratio series), all centered at 100.

    rs       = close / bench
    rs_ratio = 100 * rs / SMA(rs, wr)
    rs_mom   = 100 * rs_ratio / SMA(rs_ratio, wm)

    Returns (nan, nan, empty) when there is not enough valid history.
    """
    close = np.asarray(close, dtype=float)
    bench = np.asarray(bench, dtype=float)
    if len(close) < wr + wm or len(close) != len(bench):
        return float('nan'), float('nan'), np.array([])

    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(bench > 0, close / bench, np.nan)
    rs_s = pd.Series(rs)
    ratio = 100.0 * rs_s / rs_s.rolling(wr).mean()
    mom = 100.0 * ratio / ratio.rolling(wm).mean()

    r_last = ratio.iloc[-1]
    m_last = mom.iloc[-1]
    if pd.isna(r_last) or pd.isna(m_last):
        return float('nan'), float('nan'), np.array([])
    return float(r_last), float(m_last), ratio.values


def _ratio_streak_weeks(ratio_series: np.ndarray) -> int:
    """Trailing consecutive rising-RS-Ratio bars, expressed in weeks (5 bars)."""
    s = ratio_series[~np.isnan(ratio_series)]
    if len(s) < 2:
        return 0
    bars = 0
    for i in range(len(s) - 1, 0, -1):
        if s[i] > s[i - 1]:
            bars += 1
        else:
            break
    return bars // 5


def _sector_abbr(name: str) -> str:
    """Short plot label from a sector name (≤5 chars)."""
    cleaned = re.sub(r'[^A-Za-z ]', '', name).strip()
    if not cleaned:
        return name[:4] or '—'
    word = cleaned.split()[0]
    return word[:5]


def _sector_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower()) or 'unknown'


def _stock_node(stock: dict, bench: pd.Series, period: str) -> dict | None:
    """Compute one stock's RRG node from cached OHLCV, or None if unusable."""
    ticker = stock['ticker']
    df = load_ticker(ticker, period=period)
    if df is None or len(df) < MIN_BARS:
        return None

    b = bench.reindex(df.index, method='ffill').values
    close = df['Close'].astype(float).values
    ratio, mom, ratio_series = calc_rrg(close, b)
    if np.isnan(ratio) or np.isnan(mom):
        return None

    # 1-month price return (%)
    m1 = round((close[-1] / close[-22] - 1) * 100, 1) if len(close) >= 22 and close[-22] else 0.0

    # offset below the trailing 52-week high (%), 0 = at the high
    high = df['High'].astype(float)
    hh = float(high.rolling(252, min_periods=20).max().iloc[-1])
    off = round((close[-1] / hh - 1) * 100, 1) if hh > 0 else -100.0

    st = _ratio_streak_weeks(ratio_series)

    sector_name = stock.get('sector') or 'Unknown'
    return dict(
        tk=ticker.replace('.BK', '').replace('.AX', ''),
        sector=_sector_id(sector_name),
        sectorName=sector_name,
        ratio=round(_clamp_plot(ratio), 2),
        mom=round(_clamp_plot(mom), 2),
        m1=m1,
        off=off,
        st=int(st),
        lead=False,
    )


def build_screener(tv_stocks: list[dict], bench: pd.Series,
                   period: str = '2y') -> dict:
    """Build the full RRG universe payload for the Screener API.

    tv_stocks : pre-screened stock dicts from fetch_tv_stocks() (have 'sector')
    bench     : aligned benchmark close series (load_benchmark())
    """
    stocks: list[dict] = []
    buckets: dict[str, dict] = {}

    for stock in tv_stocks:
        node = _stock_node(stock, bench, period)
        if node is None:
            continue
        stocks.append(node)
        sid = node['sector']
        bucket = buckets.setdefault(sid, {'name': node['sectorName'], 'members': []})
        bucket['members'].append(node)

    sectors = []
    for sid, bucket in buckets.items():
        members = bucket['members']
        if not members:
            continue
        aratio = sum(m['ratio'] for m in members) / len(members)
        amom = sum(m['mom'] for m in members) / len(members)
        sectors.append(dict(
            id=sid,
            name=bucket['name'],
            abbr=_sector_abbr(bucket['name']),
            members=members,
            ratio=round(aratio, 2),
            mom=round(amom, 2),
        ))

    return dict(
        sectors=sectors,
        stocks=stocks,
        total=len(stocks),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
