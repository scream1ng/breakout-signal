"""
rrg.py — Relative Rotation Graph universe for the Screener
==========================================================
Plots every pre-screened SET stock on a rotation map built from the project's
own RS-Momentum rating (rsm.py) at two horizons:

  x = RSM-100  (established strength, ~5 months)
  y = RSM-21   (recent strength, ~1 month — the chart's "RSM")

Both are the IBD-curve rating (1–99). The map is **median-centered**: each axis
divider sits at the universe median, so dots spread across all four quadrants
(leading / improving / weakening / lagging) relative to peers, instead of
collapsing into the top half (the pre-screened universe is all-strong).

  rsm_at(close, bench, L)            -> RSM rating at the last bar over lookback L
  build_screener(tv_stocks, bench)   -> {sectors, stocks, total, generated_at}

No network: reads only the OHLCV disk cache that the EOD scan already populated.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from statistics import median

import numpy as np
import pandas as pd

from app.core.data import load_ticker
from app.core.rsm import f_calc_final_rating, calc_rsm_series

# Lookback horizons (daily bars).
L_RATIO = 100   # x-axis: established relative strength
L_MOM = 21      # y-axis: recent relative strength (= the chart's RSM)
MIN_BARS = L_RATIO + L_MOM + 10   # enough history for the slow leg

# Plot mapping — median maps to 100, each axis auto-scaled to its own spread so
# X and Y fill the frontend's 91.5–108.5 box equally (RSM-21 has a much smaller
# native spread than RSM-100, so a single shared gain would squash the Y axis).
PLOT_LO, PLOT_HI = 91.5, 108.5
PLOT_TARGET = 7.5   # plot units the 85th-pct deviation should map to (≈ fills the box)
PLOT_SPREAD_FLOOR = 3.0   # min rating-point spread, avoids blow-up when tightly clustered


def _clamp_plot(v: float) -> float:
    return max(PLOT_LO, min(PLOT_HI, v))


def _axis_gain(values: list[float], center: float) -> float:
    """Per-axis gain: maps the 85th-percentile absolute deviation to PLOT_TARGET."""
    if not values:
        return 0.16
    dev = sorted(abs(v - center) for v in values)
    p85 = dev[min(len(dev) - 1, int(len(dev) * 0.85))]
    return PLOT_TARGET / max(p85, PLOT_SPREAD_FLOOR)


def rsm_at(close: np.ndarray, bench: np.ndarray, lookback: int) -> float:
    """Project RSM rating at the final bar, comparing now vs `lookback` bars ago.

    Mirrors rsm.calc_rsm_series' formula but with a configurable horizon.
    Returns nan when there is not enough valid history.
    """
    n = len(close)
    if n < lookback + 2:
        return float('nan')
    s_now, s_p = float(close[-1]), float(close[-1 - lookback])
    b_now, b_p = float(bench[-1]), float(bench[-1 - lookback])
    if 0 in (s_p, b_p, b_now) or any(np.isnan([s_now, s_p, b_now, b_p])):
        return float('nan')
    return f_calc_final_rating((s_now / s_p) / (b_now / b_p) * 100)


def _rsm21_streak_weeks(rsm_series: np.ndarray) -> int:
    """Trailing consecutive rising-RSM bars, expressed in weeks (5 bars)."""
    s = rsm_series[~np.isnan(rsm_series)]
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
    return cleaned.split()[0][:5]


def _sector_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower()) or 'unknown'


def _stock_raw(stock: dict, bench: pd.Series, period: str) -> dict | None:
    """Compute one stock's raw RSM coords + metadata, or None if unusable.

    Plot coords (ratio/mom) are filled later in build_screener once the
    universe medians are known.
    """
    ticker = stock['ticker']
    df = load_ticker(ticker, period=period)
    if df is None or len(df) < MIN_BARS:
        return None

    b = bench.reindex(df.index, method='ffill').values
    close = df['Close'].astype(float).values

    rsm21_series = calc_rsm_series(close, b)
    finite = rsm21_series[~np.isnan(rsm21_series)]
    if len(finite) == 0:
        return None
    rsm21 = float(finite[-1])
    rsm100 = rsm_at(close, b, L_RATIO)
    if np.isnan(rsm100) or rsm21 == 0:
        return None

    # 1-month price return (%)
    m1 = round((close[-1] / close[-22] - 1) * 100, 1) if len(close) >= 22 and close[-22] else 0.0

    # offset below the trailing 52-week high (%), 0 = at the high
    high = df['High'].astype(float)
    hh = float(high.rolling(252, min_periods=20).max().iloc[-1])
    off = round((close[-1] / hh - 1) * 100, 1) if hh > 0 else -100.0

    st = _rsm21_streak_weeks(rsm21_series)

    sector_name = stock.get('sector') or 'Unknown'
    return dict(
        tk=ticker.replace('.BK', '').replace('.AX', ''),
        sector=_sector_id(sector_name),
        sectorName=sector_name,
        rsm100=round(rsm100, 1),
        rsm21=round(rsm21, 1),
        m1=m1,
        off=off,
        st=int(st),
        lead=False,
    )


def build_screener(tv_stocks: list[dict], bench: pd.Series,
                   period: str = '2y') -> dict:
    """Build the median-centered RRG universe payload for the Screener API.

    tv_stocks : pre-screened stock dicts from fetch_tv_stocks() (have 'sector')
    bench     : aligned benchmark close series (load_benchmark())
    """
    raw: list[dict] = []
    for stock in tv_stocks:
        node = _stock_raw(stock, bench, period)
        if node is not None:
            raw.append(node)

    if not raw:
        return dict(sectors=[], stocks=[], total=0,
                    generated_at=datetime.now(timezone.utc).isoformat())

    xs = [n['rsm100'] for n in raw]
    ys = [n['rsm21'] for n in raw]
    med_x, med_y = median(xs), median(ys)
    gain_x = _axis_gain(xs, med_x)
    gain_y = _axis_gain(ys, med_y)

    def _to_plot(rsm100: float, rsm21: float) -> tuple[float, float]:
        ratio = _clamp_plot(100 + (rsm100 - med_x) * gain_x)
        mom = _clamp_plot(100 + (rsm21 - med_y) * gain_y)
        return round(ratio, 2), round(mom, 2)

    stocks: list[dict] = []
    buckets: dict[str, dict] = {}
    for n in raw:
        ratio, mom = _to_plot(n['rsm100'], n['rsm21'])
        node = dict(n, ratio=ratio, mom=mom)
        stocks.append(node)
        bucket = buckets.setdefault(n['sector'], {'name': n['sectorName'], 'members': []})
        bucket['members'].append(node)

    sectors = []
    for sid, bucket in buckets.items():
        members = bucket['members']
        if not members:
            continue
        a100 = sum(m['rsm100'] for m in members) / len(members)
        a21 = sum(m['rsm21'] for m in members) / len(members)
        ratio, mom = _to_plot(a100, a21)
        sectors.append(dict(
            id=sid,
            name=bucket['name'],
            abbr=_sector_abbr(bucket['name']),
            members=members,
            rsm100=round(a100, 1),
            rsm21=round(a21, 1),
            ratio=ratio,
            mom=mom,
        ))

    return dict(
        sectors=sectors,
        stocks=stocks,
        total=len(stocks),
        median_rsm100=round(med_x, 1),
        median_rsm21=round(med_y, 1),
        gain_x=round(gain_x, 4),
        gain_y=round(gain_y, 4),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
