"""
macro.py — Global macro snapshot for the Macro Map page
=========================================================
Fetches world indices / commodities / crypto / FX via yfinance and rates each
one's recent relative strength with the project's own RS-Momentum formula
(rsm.py), benchmarked against ACWI (iShares MSCI ACWI ETF — proxy for "world
equities"). Same formula used everywhere else in this project (rsm.py,
rrg.py) — no new math introduced here.

No network on import. build_macro_payload() does all the fetching (in
parallel — yfinance calls are blocking I/O); callers (app/api/macro.py) own
caching/TTL.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.rsm import calc_rsm_series

BENCH_TICKER = 'ACWI'
HIST_BARS = 10   # trailing daily RSM-21 ratings kept per asset (drives MiniHisto)
FETCH_WORKERS = 12   # concurrent yfinance requests — these are blocking I/O calls

# region, country, iso numeric (topojson country id), abbr, index name, yfinance ticker
# ratio/mom omitted — GlobalRRG scatter from the design mockup isn't wired into the
# real page, only the choropleth/list/histograms use the RSM series below.
INDICES = [
    dict(region='Americas', ctry='United States', iso='840', abbr='US', idx='S&P 500', ticker='^GSPC'),
    dict(region='Americas', ctry='United States', iso='840', idx='Nasdaq 100', ticker='^NDX', sub=True),
    dict(region='Americas', ctry='United States', iso='840', idx='Dow Jones', ticker='^DJI', sub=True),
    dict(region='Americas', ctry='Canada', iso='124', abbr='CA', idx='TSX Composite', ticker='^GSPTSE'),
    dict(region='Americas', ctry='Brazil', iso='076', abbr='BR', idx='Bovespa', ticker='^BVSP'),
    dict(region='Americas', ctry='Mexico', iso='484', abbr='MX', idx='IPC', ticker='^MXX'),
    dict(region='Europe', ctry='United Kingdom', iso='826', abbr='UK', idx='FTSE 100', ticker='^FTSE'),
    dict(region='Europe', ctry='Germany', iso='276', abbr='DE', idx='DAX', ticker='^GDAXI'),
    dict(region='Europe', ctry='France', iso='250', abbr='FR', idx='CAC 40', ticker='^FCHI'),
    dict(region='Europe', ctry='Italy', iso='380', abbr='IT', idx='FTSE MIB', ticker='FTSEMIB.MI'),
    dict(region='Europe', ctry='Spain', iso='724', abbr='ES', idx='IBEX 35', ticker='^IBEX'),
    dict(region='Europe', ctry='Switzerland', iso='756', abbr='CH', idx='SMI', ticker='^SSMI'),
    dict(region='Asia-Pacific', ctry='Japan', iso='392', abbr='JP', idx='Nikkei 225', ticker='^N225'),
    dict(region='Asia-Pacific', ctry='China', iso='156', abbr='CN', idx='Shanghai Comp', ticker='000001.SS'),
    dict(region='Asia-Pacific', ctry='Hong Kong', iso='344', idx='Hang Seng', ticker='^HSI', noMap=True),
    dict(region='Asia-Pacific', ctry='Taiwan', iso='158', abbr='TW', idx='TAIEX', ticker='^TWII'),
    dict(region='Asia-Pacific', ctry='South Korea', iso='410', abbr='KR', idx='KOSPI', ticker='^KS11'),
    dict(region='Asia-Pacific', ctry='India', iso='356', abbr='IN', idx='Sensex', ticker='^BSESN'),
    dict(region='Asia-Pacific', ctry='Thailand', iso='764', abbr='TH', idx='SET Index', ticker='^SET.BK', home=True),
    dict(region='Asia-Pacific', ctry='Indonesia', iso='360', abbr='ID', idx='JCI', ticker='^JKSE'),
    dict(region='Asia-Pacific', ctry='Australia', iso='036', abbr='AU', idx='ASX 200', ticker='^AXJO'),
    dict(region='MEA', ctry='Saudi Arabia', iso='682', abbr='SA', idx='Tadawul', ticker='^TASI.SR'),
    dict(region='MEA', ctry='South Africa', iso='710', abbr='ZA', idx='JSE Top 40', ticker='^J200.JO'),
]

COMMODITIES = [
    dict(name='Gold', unit='/oz', ticker='GC=F'),
    dict(name='Silver', unit='/oz', ticker='SI=F'),
    dict(name='Copper', unit='/lb', ticker='HG=F'),
    dict(name='Brent', unit='/bbl', ticker='BZ=F'),
    dict(name='WTI Crude', unit='/bbl', ticker='CL=F'),
    dict(name='Nat Gas', unit='/MMBtu', ticker='NG=F'),
]

CRYPTO = [
    dict(name='Bitcoin', sym='BTC', ticker='BTC-USD'),
    dict(name='Ethereum', sym='ETH', ticker='ETH-USD'),
    dict(name='Solana', sym='SOL', ticker='SOL-USD'),
    dict(name='BNB', sym='BNB', ticker='BNB-USD'),
]

FX = [
    dict(name='Dollar Index', sym='DXY', ticker='DX-Y.NYB', dp=2),
    dict(name='EUR / USD', sym='EURUSD', ticker='EURUSD=X', dp=4),
    dict(name='USD / THB', sym='USDTHB', ticker='THB=X', dp=2),
    dict(name='USD / JPY', sym='USDJPY', ticker='JPY=X', dp=1),
]


def _fetch_close(ticker: str, period: str = '6mo') -> pd.Series | None:
    """Daily close series, indexed by date (kept — needed to align against the
    benchmark's own dates, since different markets trade different calendars)."""
    try:
        df = yf.download(ticker, period=period, interval='1d', progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        closes = df['Close'].dropna()
        if isinstance(closes, pd.DataFrame):   # yfinance sometimes returns a 1-col frame
            closes = closes.iloc[:, 0]
        closes.index = pd.DatetimeIndex(closes.index).tz_localize(None)
        return closes if len(closes) >= 2 else None
    except Exception:
        return None


def _is_hot(rsm_hist: list[float]) -> bool:
    """Strong vs world (RSM-21 >= 80) AND accelerating (rising over the last
    3 sessions) — same mechanical pattern as this project's Prime/RVOL/RSM
    criteria (CLAUDE.md), just applied to macro assets. Computed once here so
    every frontend view reads the same field instead of re-deriving it."""
    if len(rsm_hist) < 3:
        return False
    return rsm_hist[-1] >= 80 and rsm_hist[-1] > rsm_hist[-3]


def _asset_stats(closes: pd.Series, bench: pd.Series) -> dict:
    last = float(closes.iloc[-1])
    chg = round((closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2) if len(closes) >= 2 else 0.0
    wk = round((closes.iloc[-1] / closes.iloc[-6] - 1) * 100, 2) if len(closes) >= 6 else chg

    rsm_hist: list[float] = []
    if len(bench):
        # align the benchmark onto this asset's own trading dates (same pattern
        # as rrg.py's _stock_raw) — different markets/asset classes trade
        # different calendars (crypto is 7d/week, Saudi is Sun-Thu, etc.), so
        # pairing by raw array position instead of date silently miscompares
        # bars from different days.
        b_aligned = bench.reindex(closes.index, method='ffill')
        valid = b_aligned.notna()
        s_arr = closes[valid].to_numpy(dtype=float)
        b_arr = b_aligned[valid].to_numpy(dtype=float)
        if len(s_arr) >= 23:
            rsm_series = calc_rsm_series(s_arr, b_arr)
            finite = rsm_series[~np.isnan(rsm_series)]
            if len(finite):
                rsm_hist = [round(float(v), 1) for v in finite[-HIST_BARS:]]

    return dict(last=round(last, 4), chg=chg, wk=wk, rsm_hist=rsm_hist, hot=_is_hot(rsm_hist))


def build_macro_payload() -> dict:
    all_entries = INDICES + COMMODITIES + CRYPTO + FX
    tickers = [BENCH_TICKER] + [e['ticker'] for e in all_entries]

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        fetched = dict(zip(tickers, pool.map(_fetch_close, tickers)))

    bench_closes = fetched[BENCH_TICKER]
    if bench_closes is None:
        # Benchmark is required for every RSM computation below — without it
        # every asset would get rsm_hist=[]. Return an empty payload instead
        # of a fully-RSM-less one so the API layer's cache-write guard
        # (`if payload.get('indices')`) skips it and keeps serving the last
        # good cache rather than overwriting it with degraded data.
        return dict(indices=[], commodities=[], crypto=[], fx=[],
                    benchmark=BENCH_TICKER, generated_at=datetime.now(timezone.utc).isoformat())

    def _rate(entries: list[dict]) -> list[dict]:
        out = []
        for e in entries:
            closes = fetched.get(e['ticker'])
            if closes is None:
                continue
            out.append({**e, **_asset_stats(closes, bench_closes)})
        return out

    return dict(
        indices=_rate(INDICES),
        commodities=_rate(COMMODITIES),
        crypto=_rate(CRYPTO),
        fx=_rate(FX),
        benchmark=BENCH_TICKER,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
