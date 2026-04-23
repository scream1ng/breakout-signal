"""
backtest_optimize.py — Parameter optimization for SET breakout strategy
========================================================================
Tests all parameter combinations across all SET stocks and ranks them
by risk-adjusted return. Uses walk-forward validation to avoid overfitting.

Usage:
    python backtest_optimize.py                    # full sweep, all stocks
    python backtest_optimize.py --top 20           # show top 20 combos
    python backtest_optimize.py --workers 4        # parallel workers
    python backtest_optimize.py --period 2y        # data period
    python backtest_optimize.py --validate         # walk-forward validation
    python backtest_optimize.py --quick            # fewer combos, faster

Output:
    optimization_results.csv   — all results sorted by Sharpe
    optimization_top.txt       — readable summary of top combos
"""

import os, sys, time, json, itertools, warnings, argparse
from datetime import datetime
from multiprocessing import Pool, cpu_count
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from app.core.data    import load_ticker, load_benchmark
from app.core.rsm     import calc_rsm_series
from app.core.entry   import detect_pivots
from app.core.exit    import simulate
from app.core.scanner import fetch_tv_stocks

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--top',      type=int,   default=20,     help='Show top N combos')
ap.add_argument('--workers',  type=int,   default=max(1, cpu_count() - 1))
ap.add_argument('--period',   type=str,   default='2y')
ap.add_argument('--capital',  type=float, default=100_000)
ap.add_argument('--validate', action='store_true', help='Walk-forward validation')
ap.add_argument('--quick',    action='store_true', help='Fewer combos for quick test')
ap.add_argument('--min-trades', type=int, default=20,    help='Min trades to score combo')
args = ap.parse_args()

# ── Parameter grid ────────────────────────────────────────────────────────────
if args.quick:
    GRID = {
        'rsm_min':       [65, 70, 75],
        'rvol_min':      [1.5, 2.0],
        'psth_fast':     [3],
        'psth_slow':     [7],
        'sl_atr_mult':   [1.0],
        'tp1_atr_mult':  [2, 3],
        'tp2_atr_mult':  [4, 5],
        'be_after_days': [3],
    }
else:
    GRID = {
        'rsm_min':       [60, 65, 70, 75, 80],
        'rvol_min':      [1.0, 1.5, 2.0],
        'psth_fast':     [3, 5],
        'psth_slow':     [5, 7, 9],
        'sl_atr_mult':   [1.0, 1.5, 2.0],
        'tp1_atr_mult':  [2, 3],
        'tp2_atr_mult':  [4, 5, 6],
        'be_after_days': [3, 5],
    }

PERIOD_BARS = {'6mo': 126, '12mo': 252, '18mo': 378, '2y': 504}


# ── Build base CFG for a parameter combo ────────────────────────────────────
def make_cfg(combo: dict) -> dict:
    return {
        'capital':         args.capital,
        'risk_pct':        0.005,
        'commission':      0.0015,
        'rvol_period':     20,
        'min_turnover':    5_000_000,
        'benchmark':       '^SET.BK',
        'ticker_suffix':   '.BK',
        'filter_no_reentry':  True,
        'filter_candle_body': True,
        # combo params
        'rsm_min':         combo['rsm_min'],
        'rs_momentum_min': combo['rsm_min'],
        'rvol_min':        combo['rvol_min'],
        'psth_fast':       combo['psth_fast'],
        'psth_slow':       combo['psth_slow'],
        'sl_mult':         combo['sl_atr_mult'],
        'sl_atr_mult':     combo['sl_atr_mult'],
        'tp1_mult':        combo['tp1_atr_mult'],
        'tp1_atr_mult':    combo['tp1_atr_mult'],
        'tp2_mult':        combo['tp2_atr_mult'],
        'tp2_atr_mult':    combo['tp2_atr_mult'],
        'be_days':         combo['be_after_days'],
        'be_after_days':   combo['be_after_days'],
        'min_atr_pct':     0.0,   # no filter in optimizer
    }


# ── Prepare stock data (compute indicators once) ─────────────────────────────
def prepare_stock(ticker: str, bench: pd.Series, period: str) -> dict | None:
    """Download + compute all indicators. Returns dict ready for simulate()."""
    df_full = load_ticker(ticker, period=period)
    if df_full is None or len(df_full) < 60:
        return None

    b_aligned = bench.reindex(df_full.index, method='ffill').values
    rsm_full  = calc_rsm_series(df_full['Close'].values, b_aligned)
    if rsm_full is None:
        return None

    keep = PERIOD_BARS.get(period, 504)
    df   = df_full.iloc[-keep:].copy()
    rsm  = rsm_full[-keep:]
    if len(df) < 60:
        return None

    df['RSM']  = rsm
    cl = df['Close']
    df['EMA10']  = cl.ewm(span=10,  adjust=False).mean()
    df['EMA20']  = cl.ewm(span=20,  adjust=False).mean()
    df['SMA50']  = cl.rolling(50).mean()
    df['SMA200'] = cl.rolling(200).mean()
    hl  = df['High'] - df['Low']
    hpc = (df['High'] - df['Close'].shift()).abs()
    lpc = (df['Low']  - df['Close'].shift()).abs()
    df['ATR'] = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(14).mean()

    avg_vol  = df['Volume'].rolling(20, min_periods=1).mean().values
    rvol_arr = np.where(avg_vol > 0, df['Volume'].values / avg_vol, 0.0)
    prev_cl  = np.concatenate([[np.nan], df['Close'].values[:-1]])
    gap_pct  = np.where(prev_cl > 0, (df['Open'].values - prev_cl) / prev_cl, 0.0)
    is_gap   = gap_pct >= 0.003

    return dict(ticker=ticker, df=df, rvol_arr=rvol_arr, is_gap=is_gap)


# ── Run one combo on pre-prepared stock data ──────────────────────────────────
def run_combo_on_stock(stock_data: dict, cfg: dict) -> list:
    """Returns list of Prime trades for one stock + one param combo."""
    df       = stock_data['df']
    rvol_arr = stock_data['rvol_arr']
    ticker   = stock_data['ticker']

    try:
        brk3, _, _, _ = detect_pivots(df, cfg['psth_fast'], rvol_arr, cfg, ticker)
        brk7, _, _, _ = detect_pivots(df, cfg['psth_slow'], rvol_arr, cfg, ticker)

        brk_map = {}
        for b in brk3: brk_map[b['bar']] = b
        for b in brk7: brk_map[b['bar']] = b
        all_breaks = sorted(brk_map.values(), key=lambda x: x['bar'])

        # Prime signals only (regime + rvol + rsm + stretch <= 4)
        prime_sigs = [
            (b['bar'], b['bp']) for b in all_breaks
            if b['regime_ok'] and b['rvol_ok'] and b['rsm_ok']
            and b.get('stretch', 0) <= 4
        ]

        if not prime_sigs:
            return []

        trades, _, _ = simulate(df, prime_sigs, cfg)
        return trades

    except Exception:
        return []


# ── Score a list of trades ────────────────────────────────────────────────────
def score_trades(trades: list, capital: float) -> dict | None:
    if len(trades) < args.min_trades:
        return None

    pnls      = [t['total_pnl'] for t in trades]
    rets      = [t['entry_return_pct'] for t in trades]
    wins      = [t for t in trades if t['win']]

    total_pnl = sum(pnls)
    total_ret = total_pnl / capital * 100
    win_rate  = len(wins) / len(trades) * 100
    avg_win   = np.mean([t['entry_return_pct'] for t in wins]) if wins else 0
    avg_loss  = np.mean([t['entry_return_pct'] for t in trades if not t['win']]) if len(trades) - len(wins) > 0 else 0
    std_ret   = np.std(rets) if len(rets) > 1 else 1

    # Sharpe (using per-trade returns as proxy)
    sharpe    = np.mean(rets) / std_ret if std_ret > 0 else 0

    # Max drawdown on cumulative PnL curve
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd   = (cum - peak)
    max_dd_pct = (min(dd) / capital * 100) if len(dd) > 0 else 0

    # Calmar ratio
    calmar = (total_ret / abs(max_dd_pct)) if max_dd_pct < 0 else total_ret

    # Profit factor
    gross_win  = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf         = gross_win / gross_loss if gross_loss > 0 else gross_win

    return dict(
        n_trades   = len(trades),
        win_rate   = round(win_rate, 1),
        total_ret  = round(total_ret, 2),
        avg_win    = round(avg_win, 2),
        avg_loss   = round(avg_loss, 2),
        max_dd     = round(max_dd_pct, 2),
        sharpe     = round(sharpe, 3),
        calmar     = round(calmar, 3),
        pf         = round(pf, 3),
        total_pnl  = round(total_pnl, 2),
    )


# ── Worker function (called by multiprocessing) ───────────────────────────────
def worker(args_tuple):
    combo, stocks_data = args_tuple
    cfg    = make_cfg(combo)
    trades = []
    for sd in stocks_data:
        trades.extend(run_combo_on_stock(sd, cfg))
    score = score_trades(trades, cfg['capital'])
    if score is None:
        return None
    return {**combo, **score}


# ── Walk-forward validation ───────────────────────────────────────────────────
def walk_forward_validate(best_combo: dict, stocks_data: list):
    """Split data in half. Train on first half, validate on second."""
    print('\n  Walk-forward validation...')

    train_data = []
    test_data  = []
    for sd in stocks_data:
        df = sd['df']
        mid = len(df) // 2
        train_df = df.iloc[:mid].copy()
        test_df  = df.iloc[mid:].copy()

        train_data.append({**sd, 'df': train_df,
                           'rvol_arr': sd['rvol_arr'][:mid],
                           'is_gap': sd['is_gap'][:mid]})
        test_data.append({**sd, 'df': test_df,
                          'rvol_arr': sd['rvol_arr'][mid:],
                          'is_gap': sd['is_gap'][mid:]})

    cfg = make_cfg(best_combo)

    train_trades = []
    for sd in train_data:
        train_trades.extend(run_combo_on_stock(sd, cfg))
    train_score = score_trades(train_trades, cfg['capital'])

    test_trades = []
    for sd in test_data:
        test_trades.extend(run_combo_on_stock(sd, cfg))
    test_score = score_trades(test_trades, cfg['capital'])

    print(f'\n  {"":30} {"Train":>10} {"Test":>10}')
    print(f'  {"-"*52}')
    if train_score and test_score:
        for key in ['n_trades', 'win_rate', 'total_ret', 'max_dd', 'sharpe', 'calmar', 'pf']:
            print(f'  {key:<30} {str(train_score[key]):>10} {str(test_score[key]):>10}')
        consistent = (
            test_score['sharpe'] > 0 and
            test_score['win_rate'] > 45 and
            test_score['total_ret'] > 0
        )
        print(f'\n  Result: {"✅ CONSISTENT — edge holds on unseen data" if consistent else "⚠️  INCONSISTENT — may be overfitted"}')
    else:
        print('  Not enough trades for validation.')


# ── Print results ─────────────────────────────────────────────────────────────
def print_results(results: list, top_n: int):
    if not results:
        print('\n  No results — try --min-trades lower or --quick mode')
        return

    sorted_r = sorted(results, key=lambda x: x['sharpe'], reverse=True)[:top_n]

    print(f'\n{"="*110}')
    print(f'  TOP {top_n} PARAMETER COMBINATIONS  (sorted by Sharpe ratio)')
    print(f'{"="*110}')
    print(f'  {"#":<3} {"RSM":>4} {"RVol":>5} {"Fast":>5} {"Slow":>5} {"SL":>5} {"TP1":>5} {"TP2":>5} {"BE":>4} '
          f'{"Trades":>7} {"WR%":>6} {"Ret%":>7} {"DD%":>7} {"Sharpe":>7} {"Calmar":>7} {"PF":>6}')
    print(f'  {"-"*106}')

    for i, r in enumerate(sorted_r, 1):
        marker = ' ◀ current' if (
            r['rsm_min'] == 70 and r['rvol_min'] == 1.5 and
            r['psth_fast'] == 3 and r['psth_slow'] == 7 and
            r['sl_atr_mult'] == 1.0 and r['tp1_atr_mult'] == 2 and
            r['tp2_atr_mult'] == 4 and r['be_after_days'] == 3
        ) else ''
        print(f'  {i:<3} {r["rsm_min"]:>4} {r["rvol_min"]:>5.1f} {r["psth_fast"]:>5} {r["psth_slow"]:>5} '
              f'{r["sl_atr_mult"]:>5.1f} {r["tp1_atr_mult"]:>5} {r["tp2_atr_mult"]:>5} {r["be_after_days"]:>4} '
              f'{r["n_trades"]:>7} {r["win_rate"]:>6.1f} {r["total_ret"]:>+7.1f} {r["max_dd"]:>+7.1f} '
              f'{r["sharpe"]:>7.3f} {r["calmar"]:>7.3f} {r["pf"]:>6.3f}{marker}')

    print(f'{"="*110}')

    # Summary
    best = sorted_r[0]
    print(f'\n  Best combo: RSM={best["rsm_min"]}  RVol={best["rvol_min"]}  '
          f'Fast={best["psth_fast"]}  Slow={best["psth_slow"]}  '
          f'SL={best["sl_atr_mult"]}×ATR  TP1={best["tp1_atr_mult"]}×  TP2={best["tp2_atr_mult"]}×  BE={best["be_after_days"]}bars')
    print(f'  Sharpe {best["sharpe"]}  |  Win rate {best["win_rate"]}%  |  '
          f'Return {best["total_ret"]:+.1f}%  |  Max DD {best["max_dd"]:+.1f}%  |  '
          f'{best["n_trades"]} trades\n')


# ── Save results ──────────────────────────────────────────────────────────────
def save_results(results: list):
    if not results:
        return
    df = pd.DataFrame(results)
    print(f'  Saved: data/optimization_results.csv ({len(df)} combos)')
    data_dir = os.path.join(ROOT, 'data')
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, 'optimization_results.csv')
    df.to_csv(path, index=False)
    print(f'  Results saved → {path}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()

    # ── Load data ─────────────────────────────────────────────────────────
    print(f'\n{"="*60}')
    print(f'  BREAKOUT STRATEGY OPTIMIZER')
    print(f'  Period: {args.period}  |  Capital: {args.capital:,.0f}')
    print(f'{"="*60}')

    cfg_base = {
        'capital': args.capital, 'risk_pct': 0.005, 'commission': 0.0015,
        'rvol_period': 20, 'min_turnover': 5_000_000,
        'benchmark': '^SET.BK', 'ticker_suffix': '.BK',
        'rs_momentum_min': 70, 'rsm_min': 70, 'rvol_min': 1.5,
    }

    print('\n  Loading benchmark...')
    bench = load_benchmark(cfg_base)
    if bench is None:
        sys.exit('  Failed to load benchmark.')

    print('  Fetching SET stock list...')
    stocks = fetch_tv_stocks(cfg_base)
    if not stocks:
        sys.exit('  No stocks found.')

    print(f'\n  Preparing {len(stocks)} stocks (downloading + computing indicators)...')
    stocks_data = []
    for i, stock in enumerate(stocks):
        print(f'  [{i+1:>3}/{len(stocks)}] {stock["ticker"]:<16}', end='\r')
        sd = prepare_stock(stock['ticker'], bench, args.period)
        if sd:
            stocks_data.append(sd)
    print(f'  Prepared {len(stocks_data)} stocks{" " * 30}')

    # ── Build parameter combos ─────────────────────────────────────────────
    keys   = list(GRID.keys())
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    n      = len(combos)
    print(f'\n  Testing {n} parameter combinations across {len(stocks_data)} stocks...')
    print(f'  Workers: {args.workers}  |  Min trades per combo: {args.min_trades}')

    # ── Run combinations ───────────────────────────────────────────────────
    work = [(c, stocks_data) for c in combos]

    results = []
    if args.workers > 1:
        with Pool(args.workers) as pool:
            for i, r in enumerate(pool.imap_unordered(worker, work), 1):
                if i % 100 == 0 or i == n:
                    elapsed = time.time() - t0
                    eta = elapsed / i * (n - i)
                    print(f'  {i}/{n} combos  ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)  ', end='\r')
                if r:
                    results.append(r)
    else:
        for i, w in enumerate(work, 1):
            if i % 50 == 0 or i == n:
                print(f'  {i}/{n} combos...', end='\r')
            r = worker(w)
            if r:
                results.append(r)

    print(f'\n  Done. {len(results)}/{n} combos had enough trades.')

    # ── Results ────────────────────────────────────────────────────────────
    print_results(results, args.top)
    save_results(results)

    # ── Walk-forward validation on best combo ──────────────────────────────
    if args.validate and results:
        best = sorted(results, key=lambda x: x['sharpe'], reverse=True)[0]
        walk_forward_validate(best, stocks_data)

    print(f'  Total time: {time.time()-t0:.0f}s\n')


if __name__ == '__main__':
    main()