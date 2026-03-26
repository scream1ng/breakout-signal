"""
Swing Trading Scanner — Thai SET  (Pivot Breakout strategy)
============================================================
USAGE:
  python main.py              # scan + print results
  python main.py --discord    # scan + print + send to Discord
  python main.py --view       # open interactive chart in browser
  python main.py --view TOP.BK

OPTIONS:
  --period    12mo|2y          data period (default 12mo)
  --capital   100000           starting capital
  --rsm       70               minimum RS Momentum threshold
  --clear-cache                delete all cached price data
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
from core.portfolio          import simulate_portfolio
from output.chart_interactive import get_chart_data
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
ap.add_argument('ticker',        type=str,   nargs='?', default=None)
ap.add_argument('--discord',     action='store_true')
ap.add_argument('--view',        action='store_true')
ap.add_argument('--clear-cache', action='store_true', dest='clear_cache')
ap.add_argument('--period',      type=str,   default=_cfg('period',          '12mo'))
ap.add_argument('--capital',     type=float, default=_cfg('capital',         100_000))
ap.add_argument('--rsm',         type=float, default=_cfg('rs_momentum_min', 70))
ap.add_argument('--min-turnover',type=float, default=_cfg('min_turnover',    5_000_000))
ap.add_argument('--benchmark',   type=str,   default=_cfg('benchmark',       '^SET.BK'))
args = ap.parse_args()

CFG = dict(
    capital      = args.capital,
    risk_pct     = _cfg('risk_pct',      0.005),
    rsm_min      = args.rsm,
    min_turnover = args.min_turnover,
    benchmark    = args.benchmark,
    commission   = _cfg('commission',    0.0015),
    rvol_period  = _cfg('rvol_period',   20),
    rvol_min     = _cfg('rvol_min',      1.5),
    psth_fast    = _cfg('psth_fast',     3),
    psth_slow    = _cfg('psth_slow',     7),
    sl_mult      = _cfg('sl_atr_mult',   1),
    tp1_mult     = _cfg('tp1_atr_mult',  2),
    tp2_mult     = _cfg('tp2_atr_mult',  4),
    be_days      = _cfg('be_after_days', 3),
)

PERIOD      = args.period
WEB_DIR     = os.path.join(SCRIPT_DIR, 'docs')
DATE_STR    = datetime.today().strftime('%Y_%m_%d')
os.makedirs(WEB_DIR, exist_ok=True)

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

    last_bar    = len(df) - 1
    last_close  = round(float(df['Close'].iloc[-1]), 4)
    last_atr    = float(df['ATR'].iloc[-1]) if not pd.isna(df['ATR'].iloc[-1]) else 0
    rsm_last    = float(df['RSM'].iloc[-1]) if not pd.isna(df['RSM'].iloc[-1]) else 0.0
    rvol_last   = round(float(rvol_arr[-1]), 2)
    # Only suppress pending if a strong signal fired today (regime + RVOL or RSM)
    # Weak signals (SMA50 only) should not hide a stock from the watchlist
    today_fired = any(
        b['bar'] == last_bar and (b.get('rvol_ok') or b.get('rsm_ok'))
        for b in all_breaks
    )
    last_ema10  = float(df['EMA10'].iloc[-1]) if not pd.isna(df['EMA10'].iloc[-1]) else 0
    last_ema20  = float(df['EMA20'].iloc[-1]) if not pd.isna(df['EMA20'].iloc[-1]) else 0
    last_sma50  = float(df['SMA50'].iloc[-1]) if not pd.isna(df['SMA50'].iloc[-1]) else 0
    last_regime = last_close > last_sma50

    # MA position: which MAs is price above?
    above_ema10 = last_close > last_ema10
    above_ema20 = last_close > last_ema20
    above_sma50 = last_close > last_sma50

    # Watchlist: active line, in regime, no breakout today
    pending_info = None
    if pending_levels and not today_fired and last_regime:
        last_avg_vol = float(avg_vol[-1]) if len(avg_vol) > 0 else 0
        pending_info = dict(
            ticker=ticker, desc=stock['desc'], sector=stock['sector'],
            close=last_close, atr=round(last_atr, 4),
            rsm=round(rsm_last, 1), rvol=rvol_last,
            avg_volume=round(last_avg_vol),
            sma50=round(last_sma50, 4),
            levels=pending_levels,
        )

    # Today's signal: Full first, then any regime signal
    today_info = None
    today_sig  = next((b for b in all_breaks if b['bar'] == last_bar
                       and b['rsm_ok'] and b['rvol_ok'] and b['regime_ok']), None)
    if not today_sig:
        today_sig = next((b for b in all_breaks if b['bar'] == last_bar
                          and b['regime_ok']), None)
    if today_sig:
        bp  = today_sig['bp']
        atr = today_sig['atr']
        # Stretch at break price for criteria classification
        sma50_now  = float(df['SMA50'].iloc[last_bar]) if not pd.isna(df['SMA50'].iloc[last_bar]) else bp
        _atr_pct   = (atr / bp * 100) if bp > 0 else 0
        _price_dist= ((bp - sma50_now) / sma50_now * 100) if sma50_now > 0 else 0
        _stretch   = round(_price_dist / _atr_pct, 2) if _atr_pct > 0 else 0
        today_info = dict(
            ticker=ticker, desc=stock['desc'], sector=stock['sector'],
            date=today_sig['date'], kind=today_sig['kind'],
            bp=bp, close=last_close,
            sl=round(bp - atr * CFG['sl_mult'],  2),
            tp1=round(bp + atr * CFG['tp1_mult'], 2),
            tp2=round(bp + atr * CFG['tp2_mult'], 2),
            atr=atr, rsm=today_sig['rsm'], rvol=today_sig['rvol'],
            rsm_ok=today_sig['rsm_ok'], rvol_ok=today_sig['rvol_ok'],
            stretch=_stretch, tl_angle=today_sig.get('tl_angle'),
        )

    # Backtest simulations (3 filter tiers)
    def _sig(regime=True, rvol=True, rsm=True):
        return [(b['bar'], b['bp']) for b in all_breaks
                if (not regime or b['regime_ok'])
                and (not rvol   or b['rvol_ok'])
                and (not rsm    or b['rsm_ok'])]

    def _run(sig_list, label):
        ts, _, _ = simulate(df, sig_list, CFG)
        for t in ts:
            eb = t['entry_bar']; xb = t['exit_bar']
            t['entry_date']  = str(df.index[eb].date()) if hasattr(df.index[eb], 'date') else str(eb)
            t['exit_date']   = str(df.index[xb].date()) if xb is not None and hasattr(df.index[xb], 'date') else '—'
            t['filter_type'] = label
            # TP dates for portfolio partial-exit splitting
            tp1b = t.get('tp1_bar')
            tp2b = t.get('tp2_bar')
            t['tp1_date'] = str(df.index[tp1b].date()) if tp1b is not None and hasattr(df.index[tp1b], 'date') else None
            t['tp2_date'] = str(df.index[tp2b].date()) if tp2b is not None and hasattr(df.index[tp2b], 'date') else None
            # Per-tranche return % from entry price (for portfolio partial P&L)
            ep = t['entry_price']
            t['tp1_ret_pct']   = round((t['tp1']        - ep) / ep * 100, 2) if ep else 0
            t['tp2_ret_pct']   = round((t['tp2']        - ep) / ep * 100, 2) if ep else 0
            t['final_ret_pct'] = round((t.get('exit_price', ep) - ep) / ep * 100, 2) if ep else 0
            # Stretch Factor = (close - SMA50) / SMA50 / ATR%
            # Measures how many ATR multiples price is extended above SMA50
            # > 4 = overextended, skip in portfolio
            atr_val    = float(t.get('atr_val', 0))
            sma50      = float(df['SMA50'].iloc[eb]) if not pd.isna(df['SMA50'].iloc[eb]) else 0
            # Stretch at break price — matches real decision point (bp, not close)
            bp_price   = float(t.get('entry_level', t.get('entry_price', 0)))  # entry_level = bp
            atr_pct    = (atr_val / bp_price * 100) if bp_price > 0 else 0
            price_dist = ((bp_price - sma50) / sma50 * 100) if sma50 > 0 else 0
            t['stretch'] = round(price_dist / atr_pct, 2) if atr_pct > 0 else 0
            t['atr_pct'] = round(atr_pct, 2)   # keep for reference
        return ts

    # Prime = RVOL + RSM + SMA50 (highest quality — used for portfolio/backtest)
    # STR   = Prime criteria but stretch > 4 at break price
    # RVOL  = RVOL + SMA50, no RSM
    # RSM   = RSM + SMA50, no RVOL
    # SMA50 = SMA50 only
    prime_sigs = _sig(regime=True, rvol=True, rsm=True)
    # Separate STR (overextended) from Prime by stretch value
    prime_clean = [(bar, bp) for bar, bp in prime_sigs
                   if next((b for b in all_breaks if b['bar'] == bar), {}).get('stretch', 0) <= 4]
    str_sigs    = [(bar, bp) for bar, bp in prime_sigs
                   if next((b for b in all_breaks if b['bar'] == bar), {}).get('stretch', 0) > 4]

    pb_trades   = _run(prime_clean, 'Prime')
    str_trades  = _run(str_sigs,    'STR')
    rvol_trades = _run(_sig(regime=True, rvol=True, rsm=False), 'RVOL')
    rsm_trades  = _run(_sig(regime=True, rvol=False, rsm=True), 'RSM')
    sma50_trades= _run(_sig(regime=True, rvol=False, rsm=False), 'SMA50')

    # Dedup by entry_bar: Prime > STR > RVOL > RSM > SMA50
    seen_bars = {t['entry_bar'] for t in pb_trades}
    def _dedup(trades):
        out = []
        for t in trades:
            if t['entry_bar'] not in seen_bars:
                seen_bars.add(t['entry_bar'])
                out.append(t)
        return out

    all_trades_chart = (pb_trades
                        + _dedup(str_trades)
                        + _dedup(rvol_trades)
                        + _dedup(rsm_trades)
                        + _dedup(sma50_trades))

    chart_data = get_chart_data(df, ticker, stock, all_breaks,
                                hz_lines, tl_lines, rvol_arr, is_gap, CFG,
                                trades=all_trades_chart)

    rsm_now       = float(df['RSM'].iloc[-1]) if not pd.isna(df['RSM'].iloc[-1]) else 0.0
    total_pnl     = sum(t['total_pnl'] for t in pb_trades)
    total_pnl_pct = total_pnl / CFG['capital'] * 100
    win_rate      = (len([t for t in pb_trades if t['win']]) / len(pb_trades) * 100
                     if pb_trades else 0)

    return dict(
        ticker=ticker, desc=stock['desc'], sector=stock['sector'],
        rs_momentum=rsm_now,
        total_trades=len(pb_trades), total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct, win_rate=win_rate,
        today_signal=today_info, pending=pending_info,
        trades=all_trades_chart, chart_data=chart_data,
        in_regime=last_regime,
        above_ema10=above_ema10, above_ema20=above_ema20, above_sma50=above_sma50,
        last_close=last_close, last_ema10=last_ema10, last_ema20=last_ema20, last_sma50=last_sma50,
    )


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
            sig    = 'B' if r.get('today_signal') else ('W' if r.get('pending') else ' ')
            wr_str = f'{r["win_rate"]:.0f}%' if r['total_trades'] > 0 else '--'
            print(f'  {sig}  RSM {r["rs_momentum"]:>4.0f}  '
                  f'{r["total_trades"]:>2}T  WR {wr_str:>4}  '
                  f'PnL {r["total_pnl"]:>+10,.0f}')
            results.append(r)
            time.sleep(0.2)
        except Exception as e:
            skipped += 1; print(f'  ERROR: {e}')
    return results, skipped


def print_scan_results(today_signals, pending_list, results, date_str):
    """Delegate to report.py — only breakout signals in terminal."""
    from output.report import print_screener
    print_screener(today_signals, pending_list, date_str)


# ══════════════════════════════════════════════════════════════════════════════
def main():
    if args.clear_cache:
        clear_cache()
        print('  Cache cleared.')
        return

    cs = cache_stats()
    print(f'\n{"="*64}')
    print(f'  BREAKOUT SCANNER  {DATE_STR.replace("_","-")}  RSM>{CFG["rsm_min"]}  Capital {CFG["capital"]:,.0f}')
    print(f'  Cache: {cs["valid"]}/{cs["total"]} cached  BKK {cs["bkk_time"]}')
    print(f'{"="*64}')

    bench = load_benchmark(CFG)
    if bench is None:
        sys.exit('  Failed to load benchmark data.')

    # ── --view ────────────────────────────────────────────────────────────
    if args.view:
        if args.ticker:
            ticker = args.ticker
            if not ticker.endswith('.BK') and not ticker.startswith('^'):
                ticker += '.BK'
            stock = {'ticker': ticker, 'desc': ticker, 'sector': ''}
            print(f'  Processing {ticker}...')
            r = process_ticker(stock, bench)
            if r is None:
                sys.exit(f'  Could not load {ticker}')
            path = generate_combined_html([r['chart_data']], [r], WEB_DIR, DATE_STR,
                                          filename=f'{ticker.replace(".","_")}.html')
            webbrowser.open(f'file://{os.path.abspath(path)}')
        else:
            index_path = os.path.join(WEB_DIR, 'index.html')
            if os.path.exists(index_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(index_path))
                if mtime.date() == datetime.today().date():
                    print(f'  Using chart from today ({mtime.strftime("%H:%M")})')
                    webbrowser.open(f'file://{os.path.abspath(index_path)}')
                    return
            print('  Generating chart...')
            results, _ = run_full_scan(bench)
            regime_results = [r for r in results if r.get('in_regime')]
            stocks_data    = [r['chart_data'] for r in regime_results if r.get('chart_data')]
            portfolio_data = simulate_portfolio(regime_results, CFG)
            path = generate_combined_html(stocks_data, regime_results, WEB_DIR, DATE_STR,
                                          filename='index.html', portfolio=portfolio_data)
            webbrowser.open(f'file://{os.path.abspath(path)}')
        return

    # ── Default scan (+ optional --discord) ──────────────────────────────
    results, _ = run_full_scan(bench)
    today_signals = [r['today_signal'] for r in results if r.get('today_signal')]
    pending_list  = [r['pending']       for r in results if r.get('pending')]

    print_scan_results(today_signals, pending_list, results, DATE_STR)

    # ── Save watchlist.json for intraday scanner ──────────────────────────
    import json
    watchlist = []
    for r in results:
        p = r.get('pending')
        if not p:
            continue
        for lv in p['levels']:
            atr        = p.get('atr', 0)
            close      = p.get('close', 0)
            sma50      = p.get('sma50', 0)
            _atr_pct   = (atr / lv['level'] * 100) if lv['level'] > 0 else 0
            _dist      = ((lv['level'] - sma50) / sma50 * 100) if sma50 > 0 else 0
            _stretch   = round(_dist / _atr_pct, 2) if _atr_pct > 0 else 0
            watchlist.append(dict(
                ticker     = p['ticker'],
                desc       = p.get('desc', ''),
                level      = lv['level'],
                kind       = lv['kind'],
                rsm        = p.get('rsm', 0),
                atr        = atr,
                close      = close,
                rvol       = p.get('rvol', 0),
                avg_volume = p.get('avg_volume', 0),
                stretch    = _stretch,
                tl_angle   = lv.get('tl_angle'),
                date_added = DATE_STR,
            ))
    wl_path = os.path.join(SCRIPT_DIR, 'watchlist.json')
    with open(wl_path, 'w') as f:
        json.dump(watchlist, f, indent=2)
    print(f'  Watchlist saved → {len(watchlist)} levels')

    # Generate/update chart
    regime_results = [r for r in results if r.get('in_regime')]
    stocks_data    = [r['chart_data'] for r in regime_results if r.get('chart_data')]
    if stocks_data:
        portfolio_data = simulate_portfolio(regime_results, CFG)
        generate_combined_html(stocks_data, regime_results, WEB_DIR, DATE_STR,
                               filename='index.html', portfolio=portfolio_data)
        print(f'  Chart updated → python main.py --view\n')

    if args.discord:
        send_discord(today_signals, pending_list, results, DATE_STR, CFG)


if __name__ == '__main__':
    main()
