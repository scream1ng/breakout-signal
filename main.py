"""
Swing Trading Scanner - Thai SET
==================================
USAGE:
    python main.py                      -> scan full SET market
    python main.py DELTA.BK             -> scan single stock
    python main.py DELTA.BK --period 2y -> single stock, longer period
    python main.py --rs-momentum 80     -> full scan, stricter RSM filter
    python main.py --capital 200000     -> full scan, bigger capital

STRATEGY: Pivot Breakout (PB)
    Signal fires when high touches EITHER:
      (a) Horizontal extension of a recent confirmed pivot high, OR
      (b) Descending trendline connecting two consecutive Lower Highs
    Volume gate : RVol >= 1.5x 20-bar average (mandatory)
    Regime gate : Close > SMA50 on signal bar
    RSM gate    : Rolling RS Momentum > threshold (no look-ahead)
    Hard reset  : Close below SMA50 wipes all pivot memory

FILE LAYOUT:
    main.py    — CLI, data prep, orchestration, leaderboard
    entry.py   — pivot detection + signal generation
    exit.py    — trade simulation (money management)
    chart.py   — chart drawing
    rsm.py     — RS Momentum calculation
    scanner.py — TradingView fetch + benchmark download
    viewer.py  — local web chart browser
    config.py  — settings (optional override)
"""

import os, sys, warnings, argparse, time
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf
warnings.filterwarnings('ignore')

from rsm              import calc_rsm_series
from scanner          import fetch_tv_stocks, load_benchmark
from entry            import detect_pivots
from exit             import simulate
from chart            import draw_chart
from chart_interactive import draw_interactive_chart

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_cfg_path  = os.path.join(SCRIPT_DIR, 'config.py')
CFG_FILE   = {}
if os.path.exists(_cfg_path):
    _ns = {}
    exec(open(_cfg_path).read(), _ns)
    CFG_FILE = _ns.get('CFG', {})
else:
    print('  WARNING: config.py not found — using built-in defaults')

def _cfg(key, fallback):
    return CFG_FILE.get(key, fallback)

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('ticker',          type=str,   nargs='?', default=None)
ap.add_argument('--period',        type=str,   default=_cfg('period',           '12mo'))
ap.add_argument('--capital',       type=float, default=_cfg('capital',          100_000))
ap.add_argument('--risk-pct',      type=float, default=_cfg('risk_pct',         0.005))
ap.add_argument('--rs-momentum',   type=float, default=_cfg('rs_momentum_min',  70))
ap.add_argument('--min-turnover',  type=float, default=_cfg('min_turnover',     5_000_000))
ap.add_argument('--benchmark',     type=str,   default=_cfg('benchmark',        '^SET.BK'))
args = ap.parse_args()

SINGLE_TICKER = args.ticker
PERIOD        = args.period

# Build cfg dict shared across all modules
CFG = dict(
    capital       = args.capital,
    risk_pct      = args.risk_pct,
    rsm_min       = args.rs_momentum,
    min_turnover  = args.min_turnover,
    benchmark     = args.benchmark,
    commission    = _cfg('commission',    0.0015),
    rvol_period   = _cfg('rvol_period',   20),
    rvol_min      = _cfg('rvol_min',      1.5),
    psth_fast     = _cfg('psth_fast',     3),
    psth_slow     = _cfg('psth_slow',     7),
    sl_mult       = _cfg('sl_atr_mult',   1),
    tp1_mult      = _cfg('tp1_atr_mult',  2),
    tp2_mult      = _cfg('tp2_atr_mult',  4),
    be_days       = _cfg('be_after_days', 3),
)

CHARTS_DIR = os.path.join(SCRIPT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)
DATE_STR = datetime.today().strftime('%Y_%m_%d')

PERIOD_BARS = {'6mo': 126, '12mo': 252, '18mo': 378, '2y': 504}


# ══════════════════════════════════════════════════════════════════════════════
def run_ticker(stock: dict, bench: pd.Series) -> dict | None:
    """Download data, run signals, simulate trades, draw chart. Returns result dict or None."""
    ticker = stock['ticker']

    # ── Download ──────────────────────────────────────────────────────────
    raw = yf.download(ticker, period='2y', interval='1d',
                      auto_adjust=True, progress=False)
    if raw.empty: return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if 'Close' not in raw.columns: return None

    df_full = raw[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
    df_full.index = pd.to_datetime(df_full.index)
    if len(df_full) < 60: return None

    # ── RSM (computed on full 2y, then trimmed) ───────────────────────────
    b_aligned = bench.reindex(df_full.index, method='ffill').values
    rsm_full  = calc_rsm_series(df_full['Close'].values, b_aligned)
    if np.nanmax(rsm_full[-60:]) < CFG['rsm_min'] - 5:
        return None   # fast pre-filter

    # ── Trim to display period ────────────────────────────────────────────
    keep     = PERIOD_BARS.get(PERIOD, 252)
    df       = df_full.iloc[-keep:].copy()
    rsm_trim = rsm_full[-keep:]
    if len(df) < 60: return None
    df['RSM'] = rsm_trim

    # ── Indicators ────────────────────────────────────────────────────────
    cl = df['Close']
    df['EMA10']  = cl.ewm(span=10,  adjust=False).mean()
    df['EMA20']  = cl.ewm(span=20,  adjust=False).mean()
    df['SMA50']  = cl.rolling(50).mean()
    df['SMA200'] = cl.rolling(200).mean()
    hl  = df['High'] - df['Low']
    hpc = (df['High'] - df['Close'].shift()).abs()
    lpc = (df['Low']  - df['Close'].shift()).abs()
    df['ATR'] = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(14).mean()

    # ── RVol / gap arrays ─────────────────────────────────────────────────
    rvol_period = CFG['rvol_period']
    avg_vol  = df['Volume'].rolling(rvol_period, min_periods=1).mean().values
    rvol_arr = np.where(avg_vol > 0, df['Volume'].values / avg_vol, 0.0)
    prev_cl  = np.concatenate([[np.nan], df['Close'].values[:-1]])
    gap_pct  = np.where(prev_cl > 0, (df['Open'].values - prev_cl) / prev_cl, 0.0)
    is_gap   = gap_pct >= 0.003

    # ── Pivot detection (dual PSTH) — returns ALL breaks, no filters ─────
    brk3, hz3, tl3 = detect_pivots(df, CFG['psth_fast'], rvol_arr, CFG, ticker)
    brk7, hz7, tl7 = detect_pivots(df, CFG['psth_slow'], rvol_arr, CFG, ticker)

    # Merge all breaks for display (psth_slow takes priority on same bar)
    brk_map = {}
    for b in brk3: brk_map[b['bar']] = b
    for b in brk7: brk_map[b['bar']] = b
    all_breaks = sorted(brk_map.values(), key=lambda x: x['bar'])

    hz_lines = ('dual', hz3, hz7)
    tl_lines = ('dual', tl3, tl7)

    # For simulation: only use breaks that pass all gates (RSM + RVol + regime)
    pb_sig = [(b['bar'], b['bp']) for b in all_breaks
              if b['rsm_ok'] and b['rvol_ok'] and b['regime_ok']]

    # ── Simulate filtered signals ─────────────────────────────────────────
    pb_trades, pb_buy, pb_sell = simulate(df, pb_sig, CFG)

    # ── Interactive HTML chart (all breaks, clickable) ────────────────────
    draw_interactive_chart(df, ticker, stock, all_breaks,
                           hz_lines, tl_lines, rvol_arr, is_gap,
                           CFG, CHARTS_DIR, DATE_STR)

    if not pb_trades:
        print(f'  All breaks: {len(all_breaks)}  (0 pass all filters)')
        # Still return result so viewer shows the interactive chart
        rsm_now_raw = df['RSM'].iloc[-1]
        rsm_now     = float(rsm_now_raw) if not pd.isna(rsm_now_raw) else 0.0
        return dict(
            ticker=ticker, desc=stock['desc'], sector=stock['sector'],
            rs_momentum=rsm_now,
            pb_trades=0, pb_wr=0, pb_pnl=0,
            total_trades=0, total_pnl=0, total_pnl_pct=0, win_rate=0,
            chart=None, all_breaks=len(all_breaks),
        )

    # ── Chart ─────────────────────────────────────────────────────────────
    fname = draw_chart(df, ticker, stock, pb_trades, pb_buy, pb_sell,
                       hz_lines, tl_lines, rvol_arr, is_gap,
                       CFG, CHARTS_DIR, DATE_STR)

    total_pnl     = sum(t['total_pnl'] for t in pb_trades)
    total_pnl_pct = total_pnl / CFG['capital'] * 100
    win_rate      = len([t for t in pb_trades if t['total_pnl'] > 0]) / len(pb_trades) * 100
    rsm_now_raw   = df['RSM'].iloc[-1]
    rsm_now       = float(rsm_now_raw) if not pd.isna(rsm_now_raw) else 0.0

    return dict(
        ticker=ticker, desc=stock['desc'], sector=stock['sector'],
        rs_momentum=rsm_now,
        pb_trades=len(pb_trades), pb_wr=win_rate, pb_pnl=total_pnl,
        total_trades=len(pb_trades), total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct, win_rate=win_rate, chart=fname,
    )


# ── Print helpers ─────────────────────────────────────────────────────────────
def print_single(r: dict):
    SEP = '=' * 72
    print(f'\n{SEP}')
    print(f'  {r["ticker"]}   {r["desc"]}   RSM {r["rs_momentum"]:.0f}')
    print(SEP)
    print(f'  {"Strategy":<20} {"Trades":>6}  {"Win Rate":>8}  {"PnL":>12}')
    print(f'  {"-"*50}')
    print(f'  {"PB Breakout":<20} {r["pb_trades"]:>6}  {r["pb_wr"]:>7.0f}pct  {r["pb_pnl"]:>+12,.0f}')
    print(f'  {"-"*50}')
    print(f'  {"TOTAL":<20} {r["total_trades"]:>6}  {r["win_rate"]:>7.0f}pct  '
          f'{r["total_pnl"]:>+12,.0f}  ({r["total_pnl_pct"]:+.1f}pct)')
    print(f'{SEP}\n')


def print_leaderboard(results: list, skipped: int):
    capital = CFG['capital']
    if not results:
        print(f'\n  No stocks had PB trades with RSM>{CFG["rsm_min"]}.')
        return

    SEP  = '=' * 90
    SEP2 = '-' * 90
    by_pnl   = sorted(results, key=lambda r: r['total_pnl'], reverse=True)
    by_wr    = sorted(results, key=lambda r: r['win_rate'],  reverse=True)
    grand     = sum(r['total_pnl'] for r in results)
    grand_pct = grand / (capital * len(results)) * 100
    winners   = sum(1 for r in results if r['total_pnl'] > 0)

    HDR = (f'  {"#":<3} {"Ticker":<12} {"RSM":>4}  {"Sector":<16}  '
           f'{"T":>3}  {"WR":>5}  {"TOTAL PnL":>12}  {"PCT":>7}')

    def row(rank, r):
        m = 'UP' if r['total_pnl'] >= 0 else 'DN'
        s = (r['sector'] or '')[:14]
        return (f'  {rank:<3} {r["ticker"]:<12} {r["rs_momentum"]:>4.0f}  {s:<16}  '
                f'{r["total_trades"]:>3}  {r["win_rate"]:>4.0f}pct  '
                f'{m} {r["total_pnl"]:>+10,.0f}  {r["total_pnl_pct"]:>+6.1f}pct')

    print(f'\n{SEP}')
    print(f'  LEADERBOARD — Pivot Breakout   ({len(results)} stocks   {skipped} skipped/no trades)')
    print(SEP); print(HDR); print(f'  {SEP2}')
    for rank, r in enumerate(by_pnl, 1): print(row(rank, r))
    print(f'  {SEP2}')
    print(f'  {"GRAND TOTAL":<40}  {"":>3}  {"":>5}  '
          f'   {grand:>+10,.0f}  {grand_pct:>+6.1f}pct')

    print(f'\n{SEP}')
    print('  TOP 10 — Highest Win Rate')
    print(SEP); print(HDR); print(f'  {SEP2}')
    for rank, r in enumerate(by_wr[:10], 1): print(row(rank, r))

    print(f'\n{SEP}'); print('  QUICK SUMMARY'); print(SEP)
    print(f'  Stocks with PB trades  : {len(results)}   (skipped {skipped})')
    print(f'  Profitable stocks      : {winners} / {len(results)}')
    print(f'  Losing stocks          : {len(results)-winners} / {len(results)}')
    print(f'  Best stock             : {by_pnl[0]["ticker"]}  RSM {by_pnl[0]["rs_momentum"]:.0f}'
          f'  PnL {by_pnl[0]["total_pnl"]:+,.0f} ({by_pnl[0]["total_pnl_pct"]:+.1f}pct)')
    print(f'  Worst stock            : {by_pnl[-1]["ticker"]}  RSM {by_pnl[-1]["rs_momentum"]:.0f}'
          f'  PnL {by_pnl[-1]["total_pnl"]:+,.0f} ({by_pnl[-1]["total_pnl_pct"]:+.1f}pct)')
    print(f'  Best win rate          : {by_wr[0]["ticker"]}  WR {by_wr[0]["win_rate"]:.0f}pct'
          f'  Trades {by_wr[0]["total_trades"]}')
    print(f'  Grand total PnL        : {grand:+,.0f}  ({grand_pct:+.1f}pct avg per stock)')
    print(f'  Entry                  : high touches level -> fill at break price (same bar)')
    print(f'  Commission             : {CFG["commission"]*100:.2f}pct per side')
    print(f'  Charts saved to        : {CHARTS_DIR}')
    print(f'{SEP}\n')


# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{"="*72}')
if SINGLE_TICKER:
    print(f'  SINGLE STOCK   {SINGLE_TICKER}   Period: {PERIOD}   RSM>{CFG["rsm_min"]}')
else:
    print(f'  FULL SET SCAN   RSM>{CFG["rsm_min"]}   Period: {PERIOD}   Capital: {CFG["capital"]:,.0f}')
print(f'{"="*72}')

bench = load_benchmark(CFG)

if SINGLE_TICKER:
    ticker = SINGLE_TICKER
    if not ticker.endswith('.BK') and not ticker.startswith('^'):
        ticker += '.BK'
    stock = {'ticker': ticker, 'desc': ticker, 'sector': ''}
    print(f'\n  Running backtest for {ticker}...')
    r = run_ticker(stock, bench)
    if r is None:
        print(f'  No PB trades fired for {ticker} with RSM>{CFG["rsm_min"]}. '
              f'Try --rs-momentum 60')
    else:
        print_single(r)

else:
    tv_stocks = fetch_tv_stocks(CFG)
    if not tv_stocks:
        sys.exit('  No stocks passed pre-screen.')

    results = []; skipped = 0; total = len(tv_stocks)
    print(f'\n  Scanning {total} stocks...\n')

    for i, stock in enumerate(tv_stocks):
        ticker = stock['ticker']
        print(f'  [{i+1:>3}/{total}] {ticker:<14}', end='', flush=True)
        try:
            r = run_ticker(stock, bench)
            if r is None:
                skipped += 1; print('  skipped'); continue
            print(f'  RSM {r["rs_momentum"]:>4.0f}   {r["total_trades"]}T  '
                  f'WR {r["win_rate"]:.0f}pct   PnL {r["total_pnl"]:+,.0f} ({r["total_pnl_pct"]:+.1f}pct)')
            results.append(r)
            time.sleep(0.25)
        except Exception as e:
            skipped += 1; print(f'  ERROR: {e}')

    print_leaderboard(results, skipped)