"""
asx/main_asx.py — ASX Pivot Breakout Scanner
=============================================
USAGE:
  python asx/main_asx.py              # scan + print results
  python asx/main_asx.py --view       # open chart in browser
  python asx/main_asx.py --view BHP.AX

OPTIONS:
  --period    12mo|2y
  --capital   10000
  --rsm       70
  --clear-cache
"""

import os, sys, warnings, argparse, time, webbrowser
from datetime import datetime
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.data                import load_ticker, cache_stats, clear_cache
from core.rsm                 import calc_rsm_series
from core.entry               import detect_pivots
from core.exit                import simulate
from core.portfolio           import simulate_portfolio
from output.chart_interactive import get_chart_data
from output.chart_combined    import generate_combined_html
from output.report            import print_screener

# ── Config ────────────────────────────────────────────────────────────────────
_cfg_path = os.path.join(ROOT, 'asx', 'config_asx.py')
_ns = {}
exec(open(_cfg_path).read(), _ns)
CFG_FILE = _ns.get('CFG', {})

def _cfg(key, fallback):
    return CFG_FILE.get(key, fallback)

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(prog='main_asx.py')
ap.add_argument('ticker',        type=str,   nargs='?', default=None)
ap.add_argument('--view',        action='store_true')
ap.add_argument('--clear-cache', action='store_true', dest='clear_cache')
ap.add_argument('--period',      type=str,   default=_cfg('period',          '12mo'))
ap.add_argument('--capital',     type=float, default=_cfg('capital',         10_000))
ap.add_argument('--rsm',         type=float, default=_cfg('rs_momentum_min', 70))
ap.add_argument('--min-turnover',type=float, default=_cfg('min_turnover',    500_000))
ap.add_argument('--benchmark',   type=str,   default=_cfg('benchmark',       '^AXJO'))
args = ap.parse_args()

CFG = dict(
    capital         = args.capital,
    risk_pct        = _cfg('risk_pct',        0.005),
    commission      = _cfg('commission',       0.001),
    rs_momentum_min = args.rsm,
    rs_rating_min   = _cfg('rs_rating_min',   70),
    rvol_min        = _cfg('rvol_min',        1.5),
    rvol_period     = _cfg('rvol_period',     20),
    min_turnover    = args.min_turnover,
    period          = args.period,
    sl_atr_mult     = _cfg('sl_atr_mult',     1),
    tp1_atr_mult    = _cfg('tp1_atr_mult',    2),
    tp2_atr_mult    = _cfg('tp2_atr_mult',    4),
    be_after_days   = _cfg('be_after_days',   3),
    min_atr_pct     = _cfg('min_atr_pct',     2.5),
    # alias used by core/exit.py
    be_days         = _cfg('be_after_days',   3),
    psth_fast       = _cfg('psth_fast',       3),
    psth_slow       = _cfg('psth_slow',       7),
    ticker_suffix   = '.AX',
    benchmark       = args.benchmark,
    filter_no_reentry  = _cfg('filter_no_reentry',  True),
    filter_candle_body = _cfg('filter_candle_body',  True),
    # aliases used by core modules
    rsm_min         = args.rsm,
    sl_mult         = _cfg('sl_atr_mult',  1),
    tp1_mult        = _cfg('tp1_atr_mult', 2),
    tp2_mult        = _cfg('tp2_atr_mult', 4),
)

DATE_STR = datetime.now().strftime('%Y-%m-%d')
WEB_DIR  = os.path.join(ROOT, 'asx', 'docs')
os.makedirs(WEB_DIR, exist_ok=True)


# ── ASX tick size ─────────────────────────────────────────────────────────────
def set_tick(price: float) -> float:
    """ASX tick sizes."""
    if price < 0.10:  return 0.001
    if price < 2.00:  return 0.005
    return 0.01


# ── Fetch ASX stocks from TradingView ─────────────────────────────────────────
def fetch_asx_stocks() -> list:
    import requests as req
    print('  Fetching ASX stocks from TradingView...')
    url     = 'https://scanner.tradingview.com/australia/scan'
    payload = {
        'filter': [{'left': 'type', 'operation': 'equal', 'right': 'stock'}],
        'columns': ['name', 'description', 'sector', 'close',
                    'average_volume_10d_calc', 'SMA50', 'volume'],
        'sort':    {'sortBy': 'name', 'sortOrder': 'asc'},
        'range':   [0, 3000],
    }
    try:
        resp = req.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        sys.exit(f'  ERROR: TradingView fetch failed: {e}')

    rows = []
    for item in resp.json().get('data', []):
        d = item['d']
        ticker  = d[0]; desc = d[1]; sector = d[2] or 'Unknown'
        price   = d[3] or 0; avg_vol = d[4] or 0; sma50 = d[5]
        # Skip ETFs, warrants, options
        if any(x in ticker for x in ['.F', '.R', '-W', 'ETF', 'ETFS']):
            continue
        if price * avg_vol < CFG['min_turnover']:
            continue
        if sma50 and price < sma50:
            continue
        rows.append({'ticker': f'{ticker}.AX', 'desc': desc or ticker,
                     'sector': sector, 'price': price})
    print(f'  → {len(rows)} stocks pass pre-screen')
    return rows


# ── Load benchmark ────────────────────────────────────────────────────────────
def load_bench():
    import yfinance as yf
    print(f'  Loading benchmark {CFG["benchmark"]}...')
    raw = yf.download(CFG['benchmark'], period='2y', interval='1d',
                      auto_adjust=True, progress=False)
    if raw is None or len(raw) == 0:
        sys.exit('  ERROR: Could not load ASX benchmark.')
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    return raw['Close']


# ── Process single ticker ─────────────────────────────────────────────────────
def process_ticker(stock: dict, bench: pd.DataFrame):
    ticker = stock['ticker']
    df_full = load_ticker(ticker, period=CFG['period'])
    if df_full is None or len(df_full) < 60:
        return None

    b_aligned = bench.reindex(df_full.index, method='ffill').values
    rsm_full  = calc_rsm_series(df_full['Close'].values, b_aligned)
    if rsm_full is None:
        return None

    keep = {
        '6mo': 126, '12mo': 252, '18mo': 378, '2y': 504
    }.get(CFG['period'], 252)
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

    pend_map = {}
    for p in pend3: pend_map[p['kind']] = p
    for p in pend7: pend_map[p['kind']] = p
    pending_levels = list(pend_map.values())

    last_bar    = len(df) - 1
    last_close  = round(float(df['Close'].iloc[-1]), 4)
    last_atr    = float(df['ATR'].iloc[-1]) if not pd.isna(df['ATR'].iloc[-1]) else 0
    rsm_last    = float(df['RSM'].iloc[-1]) if not pd.isna(df['RSM'].iloc[-1]) else 0.0
    rvol_last   = round(float(rvol_arr[-1]), 2)
    last_sma50  = float(df['SMA50'].iloc[-1]) if not pd.isna(df['SMA50'].iloc[-1]) else 0
    last_ema10  = float(df['EMA10'].iloc[-1]) if not pd.isna(df['EMA10'].iloc[-1]) else 0
    last_ema20  = float(df['EMA20'].iloc[-1]) if not pd.isna(df['EMA20'].iloc[-1]) else 0
    last_regime = last_close > last_sma50
    above_ema10 = last_close > last_ema10
    above_ema20 = last_close > last_ema20
    above_sma50 = last_regime

    today_fired = any(
        b['bar'] == last_bar and (b.get('rvol_ok') or b.get('rsm_ok'))
        for b in all_breaks
    )

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

    today_info = None
    today_sig  = next((b for b in all_breaks if b['bar'] == last_bar
                       and b['rsm_ok'] and b['rvol_ok'] and b['regime_ok']), None)
    if not today_sig:
        today_sig = next((b for b in all_breaks if b['bar'] == last_bar
                          and b['regime_ok']), None)
    if today_sig:
        bp  = today_sig['bp']
        atr = today_sig['atr']
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
            stretch=_stretch,
        )

    # Backtest simulations — all 5 filter types with filter_type label
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
            tp1b = t.get('tp1_bar'); tp2b = t.get('tp2_bar')
            t['tp1_date'] = str(df.index[tp1b].date()) if tp1b is not None and hasattr(df.index[tp1b], 'date') else None
            t['tp2_date'] = str(df.index[tp2b].date()) if tp2b is not None and hasattr(df.index[tp2b], 'date') else None
            ep = t['entry_price']
            t['tp1_ret_pct']   = round((t['tp1']                    - ep) / ep * 100, 2) if ep else 0
            t['tp2_ret_pct']   = round((t['tp2']                    - ep) / ep * 100, 2) if ep else 0
            t['final_ret_pct'] = round((t.get('exit_price', ep)     - ep) / ep * 100, 2) if ep else 0
            atr_val    = float(t.get('atr_val', 0))
            sma50_val  = float(df['SMA50'].iloc[eb]) if not pd.isna(df['SMA50'].iloc[eb]) else 0
            bp_price   = float(t.get('entry_level', t.get('entry_price', 0)))
            atr_pct    = (atr_val / bp_price * 100) if bp_price > 0 else 0
            price_dist = ((bp_price - sma50_val) / sma50_val * 100) if sma50_val > 0 else 0
            t['stretch'] = round(price_dist / atr_pct, 2) if atr_pct > 0 else 0
            t['atr_pct'] = round(atr_pct, 2)
        return ts

    prime_sigs  = _sig(regime=True, rvol=True, rsm=True)
    prime_clean = [(bar, bp) for bar, bp in prime_sigs
                   if next((b for b in all_breaks if b['bar'] == bar), {}).get('stretch', 0) <= 4]
    str_sigs    = [(bar, bp) for bar, bp in prime_sigs
                   if next((b for b in all_breaks if b['bar'] == bar), {}).get('stretch', 0) > 4]

    pb_trades   = _run(prime_clean, 'Prime')
    str_trades  = _run(str_sigs,    'STR')
    rvol_trades = _run(_sig(regime=True, rvol=True,  rsm=False), 'RVOL')
    rsm_trades  = _run(_sig(regime=True, rvol=False, rsm=True),  'RSM')
    sma50_trades= _run(_sig(regime=True, rvol=False, rsm=False), 'SMA50')

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

    wins      = [t for t in pb_trades if t['win']]
    win_rate  = len(wins) / len(pb_trades) * 100 if pb_trades else 0
    total_pnl = sum(t['total_pnl'] for t in pb_trades)
    total_pnl_pct = total_pnl / CFG['capital'] * 100

    rsm_now = round(rsm_last, 1)

    chart_data = get_chart_data(df, ticker, stock, all_breaks,
                                hz_lines=('dual', hz3, hz7),
                                tl_lines=('dual', tl3, tl7),
                                rvol_arr=rvol_arr, cfg=CFG,
                                is_gap_arr=is_gap,
                                trades=all_trades_chart)

    return dict(
        ticker=ticker, desc=stock['desc'], sector=stock['sector'],
        rs_momentum=rsm_now,
        total_trades=len(pb_trades), total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct, win_rate=win_rate,
        today_signal=today_info, pending=pending_info,
        trades=all_trades_chart, chart_data=chart_data,
        in_regime=last_regime,
        above_ema10=above_ema10, above_ema20=above_ema20, above_sma50=above_sma50,
        last_close=last_close, last_ema10=last_ema10,
        last_ema20=last_ema20, last_sma50=last_sma50,
    )


# ── Full scan ─────────────────────────────────────────────────────────────────
def run_full_scan(bench):
    stocks  = fetch_asx_stocks()
    results = []; skipped = 0; total = len(stocks)
    print(f'\n  Scanning {total} stocks...\n')

    for i, stock in enumerate(stocks):
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


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if args.clear_cache:
        clear_cache()
        print('  Cache cleared.')
        return

    bench = load_bench()

    # Single stock view
    if args.ticker:
        ticker = args.ticker if args.ticker.endswith('.AX') else args.ticker + '.AX'
        stock  = {'ticker': ticker, 'desc': ticker, 'sector': 'Unknown'}
        r = process_ticker(stock, bench)
        if r is None:
            print(f'  No data for {ticker}'); return
        today_signals = [r['today_signal']] if r.get('today_signal') else []
        print_screener(today_signals, [], DATE_STR)
        if args.view and r.get('chart_data'):
            portfolio_data = simulate_portfolio([r], CFG)
            path = generate_combined_html([r['chart_data']], [r], WEB_DIR, DATE_STR,
                                          filename='asx_single.html', portfolio=portfolio_data, tv_prefix='ASX')
            webbrowser.open(f'file://{path}')
        return

    results, _ = run_full_scan(bench)
    today_signals = [r['today_signal'] for r in results if r.get('today_signal')]
    pending_list  = [r['pending']       for r in results if r.get('pending')]

    print_screener(today_signals, pending_list, DATE_STR)

    if args.view:
        regime_results = [r for r in results if r.get('in_regime')]
        stocks_data    = [r['chart_data'] for r in regime_results if r.get('chart_data')]
        if stocks_data:
            portfolio_data = simulate_portfolio(regime_results, CFG)
            path = generate_combined_html(stocks_data, regime_results, WEB_DIR, DATE_STR,
                                          filename='index.html', portfolio=portfolio_data, tv_prefix='ASX')
            webbrowser.open(f'file://{path}')
            print(f'  Chart → {path}')


if __name__ == '__main__':
    main()