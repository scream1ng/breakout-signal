"""
Swing Trading Scanner — Thai SET  (Pivot Breakout strategy)
============================================================
USAGE:
  python main.py                     # screener: breakout list + watchlist
  python main.py --discord           # screener + send results to Discord
  python main.py --backtest          # backtest all stocks: leaderboard + summary
  python main.py --backtest TOP.BK   # backtest single stock: trade list + summary
  python main.py --view              # open combined chart in browser
  python main.py --view TOP.BK       # open single-stock chart in browser
  python main.py --clear-cache       # delete all cached price data and exit

OPTIONS:
  --period    12mo|2y          data period (default 12mo)
  --capital   100000           starting capital
  --rsm       70               minimum RS Momentum filter
  --save                       also save individual PNG + HTML charts
"""

import os, sys, warnings, argparse, time, webbrowser
from datetime import datetime
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from core.data               import load_ticker, load_benchmark, cache_stats, clear_cache
from core.rsm                import calc_rsm_series
from core.scanner            import fetch_tv_stocks
from core.entry              import detect_pivots
from core.exit               import simulate
from output.report           import (print_screener, print_leaderboard,
                                     print_backtest_summary, print_trade_list)
from output.chart             import draw_chart
from output.chart_interactive import draw_interactive_chart, get_chart_data
from output.chart_combined    import generate_combined_html
from output.discord           import send_discord

# ── Config ────────────────────────────────────────────────────────────────────
_cfg_path = os.path.join(SCRIPT_DIR, 'config.py')
CFG_FILE  = {}
if os.path.exists(_cfg_path):
    _ns = {}
    exec(open(_cfg_path).read(), _ns)
    CFG_FILE = _ns.get('CFG', {})

def _cfg(key, fallback):
    return CFG_FILE.get(key, fallback)

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(prog='main.py')
ap.add_argument('ticker',         type=str,   nargs='?', default=None)
ap.add_argument('--backtest',     action='store_true')
ap.add_argument('--view',         action='store_true')
ap.add_argument('--clear-cache',  action='store_true', dest='clear_cache')
ap.add_argument('--period',       type=str,   default=_cfg('period',          '12mo'))
ap.add_argument('--capital',      type=float, default=_cfg('capital',         100_000))
ap.add_argument('--rsm',          type=float, default=_cfg('rs_momentum_min', 70))
ap.add_argument('--min-turnover', type=float, default=_cfg('min_turnover',    5_000_000))
ap.add_argument('--benchmark',    type=str,   default=_cfg('benchmark',       '^SET.BK'))
ap.add_argument('--save',         action='store_true')
ap.add_argument('--discord',      action='store_true')
ap.add_argument('--discord-test', action='store_true', dest='discord_test')
args = ap.parse_args()

CFG = dict(
    capital       = args.capital,
    risk_pct      = _cfg('risk_pct',         0.005),
    rsm_min       = args.rsm,
    min_turnover  = args.min_turnover,
    benchmark     = args.benchmark,
    commission    = _cfg('commission',        0.0015),
    rvol_period   = _cfg('rvol_period',       20),
    rvol_min      = _cfg('rvol_min',          1.5),
    psth_fast     = _cfg('psth_fast',         3),
    psth_slow     = _cfg('psth_slow',         7),
    sl_mult       = _cfg('sl_atr_mult',       1),
    tp1_mult      = _cfg('tp1_atr_mult',      2),
    tp2_mult      = _cfg('tp2_atr_mult',      4),
    be_days       = _cfg('be_after_days',     3),
)

PERIOD     = args.period
CHARTS_DIR = os.path.join(SCRIPT_DIR, 'output', 'charts')
WEB_DIR    = os.path.join(SCRIPT_DIR, 'docs')
DATE_STR   = datetime.today().strftime('%Y_%m_%d')
os.makedirs(CHARTS_DIR, exist_ok=True)
os.makedirs(WEB_DIR,    exist_ok=True)

PERIOD_BARS = {'6mo': 126, '12mo': 252, '18mo': 378, '2y': 504}


# ══════════════════════════════════════════════════════════════════════════════
def process_ticker(stock: dict, bench: pd.Series):
    ticker = stock['ticker']

    df_full = load_ticker(ticker)
    if df_full is None or len(df_full) < 60:
        return None

    b_aligned = bench.reindex(df_full.index, method='ffill').values
    rsm_full  = calc_rsm_series(df_full['Close'].values, b_aligned)
    if np.nanmax(rsm_full[-60:]) < CFG['rsm_min'] - 5:
        return None

    keep     = PERIOD_BARS.get(PERIOD, 252)
    df       = df_full.iloc[-keep:].copy()
    rsm_trim = rsm_full[-keep:]
    if len(df) < 60:
        return None
    df['RSM'] = rsm_trim

    cl = df['Close']
    df['EMA10']  = cl.ewm(span=10,  adjust=False).mean()
    df['EMA20']  = cl.ewm(span=20,  adjust=False).mean()
    df['SMA50']  = cl.rolling(50).mean()
    df['SMA200'] = cl.rolling(200).mean()
    hl  = df['High'] - df['Low']
    hpc = (df['High'] - df['Close'].shift()).abs()
    lpc = (df['Low']  - df['Close'].shift()).abs()
    df['ATR'] = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(14).mean()

    avg_vol  = df['Volume'].rolling(CFG['rvol_period'], min_periods=1).mean().values
    rvol_arr = np.where(avg_vol > 0, df['Volume'].values / avg_vol, 0.0)
    prev_cl  = np.concatenate([[np.nan], df['Close'].values[:-1]])
    gap_pct  = np.where(prev_cl > 0, (df['Open'].values - prev_cl) / prev_cl, 0.0)
    is_gap   = gap_pct >= 0.003

    brk3, hz3, tl3, pend3 = detect_pivots(df, CFG['psth_fast'], rvol_arr, CFG, ticker)
    brk7, hz7, tl7, pend7 = detect_pivots(df, CFG['psth_slow'], rvol_arr, CFG, ticker)

    brk_map = {}
    for b in brk3: brk_map[b['bar']] = b
    for b in brk7: brk_map[b['bar']] = b
    all_breaks = sorted(brk_map.values(), key=lambda x: x['bar'])

    hz_lines = ('dual', hz3, hz7)
    tl_lines = ('dual', tl3, tl7)

    pend_map = {}
    for p in pend3: pend_map[p['kind']] = p
    for p in pend7: pend_map[p['kind']] = p
    pending_levels = list(pend_map.values())

    last_bar   = len(df) - 1
    last_close = round(float(df['Close'].iloc[-1]), 4)
    last_atr   = float(df['ATR'].iloc[-1]) if not pd.isna(df['ATR'].iloc[-1]) else 0
    rsm_last   = float(df['RSM'].iloc[-1]) if not pd.isna(df['RSM'].iloc[-1]) else 0.0
    rvol_last  = round(float(rvol_arr[-1]), 2)
    today_fired = any(b['bar'] == last_bar for b in all_breaks)

    last_sma50  = float(df['SMA50'].iloc[-1]) if not pd.isna(df['SMA50'].iloc[-1]) else 0
    last_regime = last_close > last_sma50

    pending_info = None
    if pending_levels and not today_fired and last_regime:
        pending_info = dict(
            ticker=ticker, desc=stock['desc'], sector=stock['sector'],
            close=last_close, atr=round(last_atr, 4),
            rsm=round(rsm_last, 1), rvol=rvol_last,
            levels=pending_levels,
        )

    today_info = None
    today_sig  = next((b for b in all_breaks if b['bar'] == last_bar
                       and b['rsm_ok'] and b['rvol_ok'] and b['regime_ok']), None)
    # Also try No RSM if no Full signal
    if not today_sig:
        today_sig = next((b for b in all_breaks if b['bar'] == last_bar
                          and b['rvol_ok'] and b['regime_ok']), None)
    if today_sig:
        bp  = today_sig['bp']
        atr = today_sig['atr']
        today_info = dict(
            ticker=ticker, desc=stock['desc'], sector=stock['sector'],
            date=today_sig['date'], kind=today_sig['kind'],
            bp=bp, close=last_close,
            sl=round(bp - atr * CFG['sl_mult'],  4),
            tp1=round(bp + atr * CFG['tp1_mult'], 4),
            tp2=round(bp + atr * CFG['tp2_mult'], 4),
            atr=atr, rsm=today_sig['rsm'], rvol=today_sig['rvol'],
            rsm_ok=today_sig['rsm_ok'], rvol_ok=today_sig['rvol_ok'],
        )

    # ── 3 simulations for trade tab comparison ───────────────────────────
    def _sig(regime=True, rvol=True, rsm=True):
        return [(b['bar'], b['bp']) for b in all_breaks
                if (b['regime_ok'] if regime else True)
                and (b['rvol_ok']  if rvol   else True)
                and (b['rsm_ok']   if rsm    else True)
                and b['regime_ok']]   # always require regime

    def _run(sig_list, label):
        ts, _, _ = simulate(df, sig_list, CFG)
        for t in ts:
            eb = t['entry_bar']; xb = t['exit_bar']
            t['entry_date'] = str(df.index[eb].date()) if hasattr(df.index[eb], 'date') else str(eb)
            t['exit_date']  = str(df.index[xb].date()) if xb is not None and hasattr(df.index[xb], 'date') else '—'
            t['filter_type'] = label
        return ts

    pb_sig    = _sig(regime=True, rvol=True, rsm=True)
    pb_trades = _run(pb_sig,                           'Full')
    no_rsm_t  = _run(_sig(regime=True, rvol=True,  rsm=False),  'No RSM')
    no_rvol_t = _run(_sig(regime=True, rvol=False, rsm=False),  'Regime only')
    pb_buy    = [t['entry_bar'] for t in pb_trades]
    pb_sell   = [(t['exit_bar'], t['exit_reason']) for t in pb_trades]

    # Combine all trades for chart tab (deduplicate by entry_bar + filter)
    all_trades_chart = pb_trades + [
        t for t in no_rsm_t  if t['entry_bar'] not in {x['entry_bar'] for x in pb_trades}
    ] + [
        t for t in no_rvol_t if t['entry_bar'] not in {x['entry_bar'] for x in no_rsm_t}
        and t['entry_bar'] not in {x['entry_bar'] for x in pb_trades}
    ]

    chart_data = get_chart_data(df, ticker, stock, all_breaks,
                                hz_lines, tl_lines, rvol_arr, is_gap, CFG,
                                trades=all_trades_chart)

    if args.save:
        draw_interactive_chart(df, ticker, stock, all_breaks,
                               hz_lines, tl_lines, rvol_arr, is_gap,
                               CFG, CHARTS_DIR, DATE_STR)
        if pb_trades:
            draw_chart(df, ticker, stock, pb_trades, pb_buy, pb_sell,
                       hz_lines, tl_lines, rvol_arr, is_gap,
                       CFG, CHARTS_DIR, DATE_STR)

    rsm_now       = float(df['RSM'].iloc[-1]) if not pd.isna(df['RSM'].iloc[-1]) else 0.0
    total_pnl     = sum(t['total_pnl'] for t in pb_trades)
    total_pnl_pct = total_pnl / CFG['capital'] * 100
    win_rate      = (len([t for t in pb_trades if t['total_pnl'] > 0]) / len(pb_trades) * 100
                     if pb_trades else 0)

    return dict(
        ticker=ticker, desc=stock['desc'], sector=stock['sector'],
        rs_momentum=rsm_now,
        pb_trades=len(pb_trades), pb_wr=win_rate, pb_pnl=total_pnl,
        total_trades=len(pb_trades), total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct, win_rate=win_rate,
        today_signal=today_info, pending=pending_info,
        trades=pb_trades, chart_data=chart_data,
        in_regime=last_regime,
    )


def run_single(ticker: str, bench):
    if not ticker.endswith('.BK') and not ticker.startswith('^'):
        ticker += '.BK'
    stock = {'ticker': ticker, 'desc': ticker, 'sector': ''}
    print(f'  Processing {ticker}...', flush=True)
    return process_ticker(stock, bench)


def run_full_scan(bench):
    tv_stocks = fetch_tv_stocks(CFG)
    if not tv_stocks:
        sys.exit('  No stocks passed pre-screen.')
    results = []; skipped = 0; total = len(tv_stocks)
    print(f'\n  Scanning {total} stocks...\n')
    for i, stock in enumerate(tv_stocks):
        ticker = stock['ticker']
        print(f'  [{i+1:>3}/{total}] {ticker:<14}', end='', flush=True)
        try:
            r = process_ticker(stock, bench)
            if r is None:
                skipped += 1; print('  skipped'); continue
            sig    = '🔔' if r.get('today_signal') else ('W' if r.get('pending') else ' ')
            wr_str = f'{r["win_rate"]:.0f}%' if r['total_trades'] > 0 else '--'
            print(f'  {sig}  RSM {r["rs_momentum"]:>4.0f}  '
                  f'{r["total_trades"]:>2}T  WR {wr_str:>4}  '
                  f'PnL {r["total_pnl"]:>+10,.0f}')
            results.append(r)
            time.sleep(0.2)
        except Exception as e:
            skipped += 1; print(f'  ERROR: {e}')
    return results, skipped


def open_in_browser(path: str):
    webbrowser.open(f'file://{os.path.abspath(path)}')


# ══════════════════════════════════════════════════════════════════════════════
def main():
    if args.discord_test:
        from output.discord import _load_env, _post
        _load_env()
        import os
        url = os.environ.get('DISCORD_WEBHOOK', '').strip()
        if not url:
            print('  ⚠  DISCORD_WEBHOOK not found in .env')
            return
        ok = _post(url, '✅ PB Scanner webhook test OK')
        print(f'  Result: {"SUCCESS" if ok else "FAILED"}')
        return

    if args.clear_cache:
        clear_cache()
        print('  Cache cleared.')
        return

    cs = cache_stats()
    print(f'\n{"="*64}')
    print(f'  PB SCANNER  {DATE_STR.replace("_","-")}  '
          f'RSM>{CFG["rsm_min"]}  Capital {CFG["capital"]:,.0f}')
    print(f'  Cache: {cs["valid"]}/{cs["total"]} stocks cached  BKK {cs["bkk_time"]}')
    if args.save: print(f'  Charts: {CHARTS_DIR}')
    print(f'{"="*64}')

    bench = load_benchmark(CFG)
    if bench is None:
        sys.exit('  Failed to load benchmark data.')

    # ── --view ────────────────────────────────────────────────────────────
    if args.view:
        if args.ticker:
            r = run_single(args.ticker, bench)
            if r is None:
                sys.exit(f'  Could not load {args.ticker}')
            stocks_data = [r['chart_data']]
            path = generate_combined_html(stocks_data, [r], WEB_DIR, DATE_STR,
                                          filename=f'{args.ticker.replace(".","_")}.html')
            open_in_browser(path)
        else:
            index_path = os.path.join(WEB_DIR, 'index.html')
            if os.path.exists(index_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(index_path))
                if mtime.date() == datetime.today().date():
                    print(f'  Using chart from today ({mtime.strftime("%H:%M")})')
                    open_in_browser(index_path)
                    return
            print('  Generating combined chart...')
            results, skipped = run_full_scan(bench)
            stocks_data = [r['chart_data'] for r in results if r.get('chart_data')]
            path = generate_combined_html(stocks_data, results, WEB_DIR, DATE_STR,
                                          filename='index.html')
            open_in_browser(path)
        return

    # ── --backtest ────────────────────────────────────────────────────────
    if args.backtest:
        if args.ticker:
            r = run_single(args.ticker, bench)
            if r is None:
                sys.exit(f'  No data for {args.ticker}. Try --rsm 60')
            print_trade_list(r)
            print_backtest_summary([r], CFG)
        else:
            results, skipped = run_full_scan(bench)
            print_leaderboard(results, skipped, CFG)
            print_backtest_summary(results, CFG)
        return

    # ── Default: screener ─────────────────────────────────────────────────
    results, skipped = run_full_scan(bench)
    today_signals = [r['today_signal'] for r in results if r.get('today_signal')]
    pending_list  = [r['pending']       for r in results if r.get('pending')]
    print_screener(today_signals, pending_list, DATE_STR)

    # Only show stocks currently above SMA50 in the chart
    regime_results = [r for r in results if r.get('in_regime')]
    stocks_data = [r['chart_data'] for r in regime_results if r.get('chart_data')]
    if stocks_data:
        path = generate_combined_html(stocks_data, regime_results, WEB_DIR, DATE_STR,
                                      filename='index.html')
        print(f'  📊 Chart updated → run  python main.py --view  to open\n')

    if args.discord:
        send_discord(today_signals, pending_list, results, DATE_STR, CFG)


if __name__ == '__main__':
    main()