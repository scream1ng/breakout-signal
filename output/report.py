"""
output/report.py — All terminal printing functions
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── ANSI colours ───────────────────────────────────────────────────────────────
R  = '\033[91m'; G = '\033[92m'; Y = '\033[93m'; B = '\033[94m'
M  = '\033[95m'; C = '\033[96m'; W = '\033[97m'; DIM = '\033[2m'; RST = '\033[0m'


def _criteria_label(sig: dict) -> str:
    stretch = sig.get('stretch', 0)
    rvol_ok = sig.get('rvol_ok', False)
    rsm_ok  = sig.get('rsm_ok',  False)
    if stretch > 4:        return 'STR'
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def _criteria_color(label: str) -> str:
    return {'Prime': M, 'STR': R, 'RVOL': B, 'RSM': G, 'SMA50': Y}.get(label, W)


def _criteria_sort_key(sig: dict) -> int:
    return {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}.get(
        _criteria_label(sig), 9)


def _kind_label(s: dict) -> str:
    if s.get('kind') == 'tl':
        ang = s.get('tl_angle')
        return f"TL ({ang:.0f}\u00b0)" if ang is not None else 'TL'
    return 'Hz'


# ── Thresholds (read from config at import time) ────────────────────────────
try:
    from config import CFG as _CFG
except ImportError:
    _CFG = {}
_RVOL_MIN = _CFG.get('rvol_min', 1.5)
_RSM_MIN  = _CFG.get('rs_momentum_min', 70)

def _tk(ok): return f'{G}✓{RST}' if ok else f'{R}✗{RST}'

SCREEN_HDR = (
    f'  {"Ticker":<8}  {"T":<10}  {"Crit":<6}  {"Level":>8}  {"Close":>8}  {"RVol":>9}  {"RSM":>7}  {"STR":>8}'
)


def _screen_row(s: dict, crit_label: str) -> str:
    ticker   = s['ticker'].replace('.BK', '').replace('.AX', '')
    kind     = _kind_label(s)
    stretch  = s.get('stretch', 0)
    rvol     = s.get('rvol', 0)
    rsm      = s.get('rsm', 0)
    col      = _criteria_color(crit_label)
    str_col  = R if stretch > 4 else G
    str_disp = f'{stretch:.1f}x' if stretch else '—'
    rvol_str = f'{rvol:>5.1f}x{_tk(rvol >= _RVOL_MIN)}'
    rsm_str  = f'{rsm:>4.0f}{_tk(rsm  >= _RSM_MIN)}'
    str_str  = f'{str_col}{str_disp:>5}{_tk(stretch <= 4)}{RST}'
    return (
        f'  {col}{ticker:<8}{RST}  {kind:<10}  {col}{crit_label:<6}{RST}  '
        f'{s.get("bp",0):>8.2f}  {s.get("close",s.get("bp",0)):>8.2f}  '
        f'{rvol_str}  {rsm_str}  {str_str}'
    )


def print_screener(signals: list, pending: list, date_str: str):
    today = date_str.replace('_', '-')
    SEP = '=' * 74; SEP2 = '-' * 74

    print(f'\n{SEP}')
    print(f'  {W}END OF DAY SCAN  |  {today}{RST}  —  {len(signals)} breakout{"s" if len(signals)!=1 else ""}')
    print(SEP)
    if signals:
        print(SCREEN_HDR); print(f'  {SEP2}')
        last_crit = None
        for s in sorted(signals, key=lambda x: (_criteria_sort_key(x), x['ticker'])):
            crit = _criteria_label(s)
            if last_crit is not None and crit != last_crit:
                print()
            last_crit = crit
            print(_screen_row(s, crit))
    else:
        print(f'  No breakouts today.')
    print(f'{SEP}\n')


INTRADAY_HDR = (
    f'  {"Ticker":<8}  {"T":<10}  {"Crit":<6}  {"Level":>8}  {"Close":>8}  {"ProjRVol":>10}  {"RVol":>9}  {"RSM":>7}  {"STR":>8}'
)


def print_intraday(signals: list, date_str: str, time_str: str):
    SEP = '=' * 90; SEP2 = '-' * 90
    sort_key = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}

    print(f'\n{SEP}')
    print(f'  {W}INTRADAY SCAN  |  {date_str}  {time_str} BKK{RST}  —  {len(signals)} breakout{"s" if len(signals)!=1 else ""}')
    print(SEP)
    if signals:
        print(INTRADAY_HDR); print(f'  {SEP2}')
        last_crit = None
        for s in sorted(signals, key=lambda x: (sort_key.get(x['criteria'], 9), x['ticker'])):
            crit      = s['criteria']
            col       = _criteria_color(crit)
            stretch   = s.get('stretch', 0)
            str_col   = R if stretch > 4 else G
            str_disp  = f'{stretch:.1f}x' if stretch else '—'
            cur_rvol  = s.get('cur_rvol', 0)
            proj_rvol = s.get('proj_rvol', 0)
            rsm       = s.get('rsm', 0)

            proj_str = f'{proj_rvol:>8.1f}x{_tk(proj_rvol >= _RVOL_MIN)}'
            rvol_str = f'{cur_rvol:>5.1f}x{_tk(cur_rvol  >= _RVOL_MIN)}'
            rsm_str  = f'{rsm:>4.0f}{_tk(rsm >= _RSM_MIN)}'
            str_str  = f'{str_col}{str_disp:>5}{_tk(stretch <= 4)}{RST}'

            if last_crit is not None and crit != last_crit:
                print()
            last_crit = crit
            print(
                f'  {col}{s["ticker"]:<8}{RST}  {_kind_label(s):<10}  {col}{crit:<6}{RST}  '
                f'{s["level"]:>8.2f}  {s["close"]:>8.2f}  '
                f'{proj_str}  {rvol_str}  {rsm_str}  {str_str}'
            )
    else:
        print(f'  No breakouts detected.')
    print(f'{SEP}\n')


def print_leaderboard(results: list, skipped: int, cfg: dict):
    capital = cfg['capital']
    SEP = '=' * 92; SEP2 = '-' * 92
    if not results:
        print(f'\n  No stocks had trades with RSM>{cfg["rsm_min"]}.'); return

    by_pnl = sorted(results, key=lambda r: r['total_pnl'], reverse=True)
    grand  = sum(r['total_pnl'] for r in results)
    HDR = (f'  {"#":<3} {"Ticker":<12} {"RSM":>4}  '
           f'{"Trades":>6}  {"WR":>6}  {"PnL":>12}  {"PnL%":>7}')

    def row(rank, r):
        arrow = f'{G}▲{RST}' if r['total_pnl'] >= 0 else f'{R}▼{RST}'
        wr_str= f'{r["win_rate"]:.0f}%' if r['total_trades'] > 0 else '--'
        pc    = G if r['total_pnl'] >= 0 else R
        return (f'  {rank:<3} {r["ticker"]:<12} {r["rs_momentum"]:>4.0f}  '
                f'{r["total_trades"]:>6}  {wr_str:>6}  '
                f'{arrow} {pc}{r["total_pnl"]:>+10,.0f}  {r["total_pnl_pct"]:>+6.1f}%{RST}')

    print(f'\n{SEP}')
    print(f'  BREAKOUT SCANNER — Leaderboard   ({len(results)} stocks  {skipped} skipped)')
    print(SEP); print(HDR); print(f'  {SEP2}')
    for rank, r in enumerate(by_pnl, 1):
        print(row(rank, r))
    print(f'  {SEP2}')
    gc = G if grand >= 0 else R
    print(f'  {"GRAND TOTAL":<47}  {gc}{grand:>+10,.0f}  {grand/capital*100:>+6.1f}%{RST}')
    print(f'{SEP}\n')


def print_backtest_summary(results: list, cfg: dict):
    all_trades = [t for r in results for t in r.get('trades', [])]
    if not all_trades: print('  No trades found.'); return

    capital = cfg['capital']
    SEP = '=' * 56
    win_trades  = [t for t in all_trades if t['total_pnl'] > 0]
    loss_trades = [t for t in all_trades if t['total_pnl'] <= 0]
    n_total = len(all_trades); n_wins = len(win_trades); n_losses = len(loss_trades)
    win_pct = n_wins / n_total * 100 if n_total else 0

    avg_gain = sum(t['entry_return_pct'] for t in win_trades)  / n_wins   if n_wins   else 0
    avg_loss = sum(t['entry_return_pct'] for t in loss_trades) / n_losses if n_losses else 0
    max_gain = max((t['entry_return_pct'] for t in win_trades),  default=0)
    max_loss = min((t['entry_return_pct'] for t in loss_trades), default=0)
    grand    = sum(r['total_pnl'] for r in results)
    grand_pct= grand / capital * 100

    entry_dates = [t['entry_date'] for t in all_trades if t.get('entry_date') and 'bar' not in str(t['entry_date'])]
    exit_dates  = [t['exit_date']  for t in all_trades if t.get('exit_date') and str(t.get('exit_date','')) != '—']
    date_from = min(entry_dates) if entry_dates else '—'
    date_to   = max(exit_dates)  if exit_dates  else '—'
    gc = G if grand >= 0 else R

    print(f'\n{SEP}')
    print(f'  {W}BACKTEST SUMMARY{RST}')
    print(SEP)
    print(f'  Period        : {date_from}  →  {date_to}')
    print(f'  Trades        : {n_total}')
    print(f'  Win / Loss    : {G}{n_wins}{RST} / {R}{n_losses}{RST}  ({win_pct:.0f}% WR)')
    print(f'')
    print(f'  Avg Gain %    : {G}{avg_gain:+.2f}%{RST}')
    print(f'  Avg Loss %    : {R}{avg_loss:+.2f}%{RST}')
    print(f'  Max Gain %    : {G}{max_gain:+.2f}%{RST}')
    print(f'  Max Loss %    : {R}{max_loss:+.2f}%{RST}')
    print(f'')
    print(f'  Total PnL     : {gc}{grand:+,.0f}{RST}')
    print(f'  Total PnL %   : {gc}{grand_pct:+.2f}%{RST}  (of {capital:,.0f} capital)')
    print(f'{SEP}\n')


def print_sector_rotation(results: list, date_str: str):
    """Print a sector rotation summary grouped by sector, sorted by avg RSM."""
    from collections import defaultdict

    sectors = defaultdict(lambda: dict(
        stocks=0, rsm_sum=0.0, rsm_count=0,
        in_regime=0, watchlist=0, breakouts=0,
    ))

    for r in results:
        sec = (r.get('sector') or 'Unknown').strip() or 'Unknown'
        s   = sectors[sec]
        s['stocks'] += 1
        rsm = r.get('rs_momentum', 0)
        if rsm and rsm > 0:
            s['rsm_sum']   += rsm
            s['rsm_count'] += 1
        if r.get('in_regime'):
            s['in_regime'] += 1
        if r.get('pending'):
            s['watchlist'] += 1
        if r.get('today_signal'):
            s['breakouts'] += 1

    if not sectors:
        return

    rows = []
    for sec, s in sectors.items():
        avg_rsm = s['rsm_sum'] / s['rsm_count'] if s['rsm_count'] else 0
        rows.append((sec, s, avg_rsm))
    rows.sort(key=lambda x: x[2], reverse=True)

    today = date_str.replace('_', '-')
    SEP  = '=' * 76
    SEP2 = '-' * 76
    HDR  = (f'  {"Sector":<28}  {"Stocks":>6}  {"AvgRSM":>7}  '
            f'{"Regime":>7}  {"Watch":>5}  {"Break":>5}')

    print(f'\n{SEP}')
    print(f'  {W}SECTOR ROTATION  |  {today}{RST}')
    print(SEP)
    print(HDR)
    print(f'  {SEP2}')

    for sec, s, avg_rsm in rows:
        n       = s['stocks']
        regime  = s['in_regime']
        watch   = s['watchlist']
        brk     = s['breakouts']

        # Colour-code by average RSM strength (thresholds from config)
        if avg_rsm >= _RSM_MIN:
            dot = f'{G}●{RST}'
            col = G
        elif avg_rsm >= _RSM_MIN - 20:
            dot = f'{Y}●{RST}'
            col = Y
        else:
            dot = f'{DIM}○{RST}'
            col = DIM

        regime_str = f'{regime}/{n}'
        brk_str    = f'{M}{brk}{RST}' if brk else f'{DIM}{brk}{RST}'
        watch_str  = f'{C}{watch}{RST}' if watch else f'{DIM}{watch}{RST}'
        rsm_str    = f'{col}{avg_rsm:>6.1f}{RST}'

        print(f'  {dot} {sec:<28}  {n:>6}  {rsm_str}  '
              f'{regime_str:>7}  {watch_str:>14}  {brk_str:>14}')

    print(f'{SEP}\n')


def print_trade_list(r: dict):

    trades = r.get('trades', [])
    SEP = '=' * 86; SEP2 = '-' * 86
    print(f'\n{SEP}')
    print(f'  {r["ticker"]}   {r["desc"]}   RSM {r["rs_momentum"]:.0f}   '
          f'{len(trades)} trade(s)   WR {r["win_rate"]:.0f}%   '
          f'Total PnL {r["total_pnl"]:+,.0f} ({r["total_pnl_pct"]:+.1f}%)')
    print(SEP)
    if not trades:
        print(f'  No trades in this period.'); print(f'{SEP}\n'); return

    exit_lbl = {'SL': 'SL', 'EMA10': 'MA10', 'End': 'End', 'Open': 'Open'}
    HDR = (f'  {"#":<3} {"Entry":<12} {"Exit":<12} '
           f'{"Buy":>8} {"Sell":>8} {"SL":>8} {"TP1":>8} {"TP2":>8} {"Return%":>8}  Reason')
    print(HDR); print(f'  {SEP2}')

    win_t = []; loss_t = []
    for n, t in enumerate(trades, 1):
        ret_pct = t.get('entry_return_pct', 0)
        win     = t['total_pnl'] > 0
        marker  = f'{G}✓{RST}' if win else f'{R}✗{RST}'
        rsn     = exit_lbl.get(t['exit_reason'], t['exit_reason'])
        tp1_str = f'{t["tp1"]:.3f}' if t.get('tp1') else '—'
        tp2_str = f'{t["tp2"]:.3f}' if t.get('tp2') else '—'
        xp_str  = f'{t["exit_price"]:.3f}' if t.get('exit_price') else '—'
        rc      = G if ret_pct >= 0 else R
        print(f'  {n:<3} {t.get("entry_date","—"):<12} {t.get("exit_date","—"):<12} '
              f'{t["entry_price"]:>8.3f} {xp_str:>8} {t["sl"]:>8.3f} '
              f'{tp1_str:>8} {tp2_str:>8} {rc}{ret_pct:>+7.1f}%{RST}  {rsn} {marker}')
        (win_t if win else loss_t).append(t)

    print(f'  {SEP2}')
    avg_g = sum(t['entry_return_pct'] for t in win_t)  / len(win_t)  if win_t  else 0
    avg_l = sum(t['entry_return_pct'] for t in loss_t) / len(loss_t) if loss_t else 0
    max_g = max((t['entry_return_pct'] for t in win_t),  default=0)
    max_l = min((t['entry_return_pct'] for t in loss_t), default=0)
    print(f'  Wins {G}{len(win_t)}{RST}  Losses {R}{len(loss_t)}{RST}  '
          f'Avg gain {G}{avg_g:+.1f}%{RST}  Avg loss {R}{avg_l:+.1f}%{RST}  '
          f'Max gain {G}{max_g:+.1f}%{RST}  Max loss {R}{max_l:+.1f}%{RST}')
    print(f'{SEP}\n')