"""
output/report.py — All terminal printing functions
  print_screener(signals, pending, date_str)
  print_leaderboard(results, skipped, cfg)
  print_backtest_summary(results, cfg)
  print_trade_list(r)
"""


# ── Shared column header: Ticker first ────────────────────────────────────────
#   Ticker | Type | Level | Close | Gap% | RVol | RSM | ATR%
SCREEN_HDR = (
    f'  {"Ticker":<12} {"Type":<12} {"Level":>8}  {"Close":>8}  '
    f'{"Gap%":>6}  {"RVol":>5}  {"RSM":>5}  {"ATR%":>5}  {"Sector"}'
)


def _screen_row(ticker, kind, level, close, rvol, rsm, atr, sector=''):
    gap_pct  = (level - close) / close * 100
    atr_pct  = atr / close * 100 if close else 0
    kind_lbl = {'hz': 'Horiz', 'tl': 'TL'}.get(kind, kind)
    return (
        f'  {ticker:<12} {kind_lbl:<12} {level:>8.3f}  {close:>8.3f}  '
        f'{gap_pct:>+5.1f}%  {rvol:>4.1f}x  {rsm:>5.0f}  {atr_pct:>4.1f}%'
        + (f'  {sector[:16]}' if sector else '')
    )


# ── Screener ───────────────────────────────────────────────────────────────────
def print_screener(signals: list, pending: list, date_str: str):
    today = date_str.replace('_', '-')
    SEP   = '=' * 84
    SEP2  = '-' * 84

    # ── BREAKOUT LIST — sorted A→Z by ticker ─────────────────────────────
    print(f'\n{SEP}')
    print(f'  BREAKOUT LIST  [{today}]  —  {len(signals)} triggered')
    print(f'  (stocks that broke above a pivot level today with RVol + RSM confirmed)')
    print(SEP)
    if signals:
        print(SCREEN_HDR)
        print(f'  {SEP2}')
        for s in sorted(signals, key=lambda x: x['ticker']):
            sl_pct  = (s['sl']  - s['bp']) / s['bp'] * 100
            tp1_pct = (s['tp1'] - s['bp']) / s['bp'] * 100
            print(_screen_row(
                s['ticker'], s['kind'], s['bp'],
                s.get('close', s['bp']), s['rvol'], s['rsm'], s['atr'],
                s.get('sector', ''),
            ))
            print(f'  {"":12} {"":12}  '
                  f'SL {s["sl"]:>8.3f} ({sl_pct:+.1f}%)  '
                  f'TP1 {s["tp1"]:>8.3f} ({tp1_pct:+.1f}%)')
    else:
        print(f'  No breakouts today.')
    print(f'{SEP}\n')

    # ── WATCHLIST — sorted A→Z by ticker ─────────────────────────────────
    print(f'{SEP}')
    print(f'  WATCHLIST  [{today}]  —  {len(pending)} stocks near a breakout level')
    print(f'  (active pivot/trendline lines approaching — no breakout yet)')
    print(SEP)
    if pending:
        print(SCREEN_HDR)
        print(f'  {SEP2}')
        for p in sorted(pending, key=lambda x: x['ticker']):
            for lv in p['levels']:
                atr_val = p.get('atr', lv['level'] * 0.02)
                print(_screen_row(
                    p['ticker'], lv['kind'], lv['level'],
                    p['close'], p['rvol'], p['rsm'], atr_val,
                    p.get('sector', ''),
                ))
    else:
        print(f'  No stocks on watchlist.')
    print(f'{SEP}\n')


# ── Leaderboard ────────────────────────────────────────────────────────────────
def print_leaderboard(results: list, skipped: int, cfg: dict):
    capital = cfg['capital']
    SEP     = '=' * 92
    SEP2    = '-' * 92

    if not results:
        print(f'\n  No stocks had trades with RSM>{cfg["rsm_min"]}.')
        return

    by_pnl = sorted(results, key=lambda r: r['total_pnl'], reverse=True)
    grand  = sum(r['total_pnl'] for r in results)

    HDR = (f'  {"#":<3} {"Ticker":<12} {"RSM":>4}  {"Sector":<16}  '
           f'{"Trades":>6}  {"WR":>6}  {"PnL":>12}  {"PnL%":>7}')

    def row(rank, r):
        arrow  = '▲' if r['total_pnl'] >= 0 else '▼'
        s      = (r['sector'] or '')[:14]
        wr_str = f'{r["win_rate"]:.0f}%' if r['total_trades'] > 0 else '--'
        return (f'  {rank:<3} {r["ticker"]:<12} {r["rs_momentum"]:>4.0f}  {s:<16}  '
                f'{r["total_trades"]:>6}  {wr_str:>6}  '
                f'{arrow} {r["total_pnl"]:>+10,.0f}  {r["total_pnl_pct"]:>+6.1f}%')

    print(f'\n{SEP}')
    print(f'  LEADERBOARD — Pivot Breakout   ({len(results)} stocks  {skipped} skipped)')
    print(SEP); print(HDR); print(f'  {SEP2}')
    for rank, r in enumerate(by_pnl, 1):
        print(row(rank, r))
    print(f'  {SEP2}')
    print(f'  {"GRAND TOTAL":<47}  {grand:>+10,.0f}  {grand/capital*100:>+6.1f}%')
    print(f'{SEP}\n')


# ── Backtest summary ───────────────────────────────────────────────────────────
def print_backtest_summary(results: list, cfg: dict):
    all_trades = [t for r in results for t in r.get('trades', [])]
    if not all_trades:
        print('  No trades found.')
        return

    capital     = cfg['capital']
    SEP         = '=' * 56
    win_trades  = [t for t in all_trades if t['total_pnl'] > 0]
    loss_trades = [t for t in all_trades if t['total_pnl'] <= 0]
    n_total     = len(all_trades)
    n_wins      = len(win_trades)
    n_losses    = len(loss_trades)
    win_pct     = n_wins   / n_total * 100 if n_total else 0
    loss_pct    = n_losses / n_total * 100 if n_total else 0

    avg_gain_pct = sum(t['entry_return_pct'] for t in win_trades)  / n_wins   if n_wins   else 0
    avg_loss_pct = sum(t['entry_return_pct'] for t in loss_trades) / n_losses if n_losses else 0
    max_gain_pct = max((t['entry_return_pct'] for t in win_trades),  default=0)
    max_loss_pct = min((t['entry_return_pct'] for t in loss_trades), default=0)

    grand     = sum(r['total_pnl'] for r in results)
    grand_pct = grand / capital * 100

    entry_dates = [t['entry_date'] for t in all_trades
                   if t.get('entry_date') and 'bar' not in str(t['entry_date'])]
    exit_dates  = [t['exit_date']  for t in all_trades
                   if t.get('exit_date') and str(t.get('exit_date','')) != '—']
    date_from   = min(entry_dates) if entry_dates else '—'
    date_to     = max(exit_dates)  if exit_dates  else '—'

    print(f'\n{SEP}')
    print(f'  BACKTEST SUMMARY')
    print(SEP)
    print(f'  Period          : {date_from}  →  {date_to}')
    print(f'  Trades          : {n_total}')
    print(f'  Wins            : {n_wins}')
    print(f'  Losses          : {n_losses}')
    print(f'  Win Rate        : {win_pct:.1f}%')
    print(f'  Loss Rate       : {loss_pct:.1f}%')
    print(f'')
    print(f'  Avg Gain %      : {avg_gain_pct:+.2f}%  (from entry)')
    print(f'  Avg Loss %      : {avg_loss_pct:+.2f}%  (from entry)')
    print(f'  Max Gain %      : {max_gain_pct:+.2f}%')
    print(f'  Max Loss %      : {max_loss_pct:+.2f}%')
    print(f'')
    print(f'  Total PnL       : {grand:+,.0f}')
    print(f'  Total PnL %     : {grand_pct:+.2f}%  (of {capital:,.0f} capital)')
    print(f'{SEP}\n')


# ── Single-stock trade list ────────────────────────────────────────────────────
def print_trade_list(r: dict):
    trades = r.get('trades', [])
    SEP    = '=' * 86
    SEP2   = '-' * 86

    print(f'\n{SEP}')
    print(f'  {r["ticker"]}   {r["desc"]}   RSM {r["rs_momentum"]:.0f}   '
          f'{len(trades)} trade(s)   WR {r["win_rate"]:.0f}%   '
          f'Total PnL {r["total_pnl"]:+,.0f} ({r["total_pnl_pct"]:+.1f}%)')
    print(SEP)

    if not trades:
        print(f'  No trades in this period.')
        print(f'{SEP}\n')
        return

    exit_lbl = {'SL': 'SL', 'EMA10': 'MA10', 'End': 'End', 'Open': 'Open'}
    HDR = (f'  {"#":<3} {"Entry":<12} {"Exit":<12} '
           f'{"Buy":>8} {"Sell":>8} {"SL":>8} {"TP1":>8} {"TP2":>8} '
           f'{"Return%":>8}  Reason')
    print(HDR)
    print(f'  {SEP2}')

    win_trades  = []
    loss_trades = []
    for n, t in enumerate(trades, 1):
        ret_pct = t.get('entry_return_pct', 0)
        win     = t['total_pnl'] > 0
        marker  = '✓' if win else '✗'
        rsn     = exit_lbl.get(t['exit_reason'], t['exit_reason'])
        tp1_str = f'{t["tp1"]:.3f}' if t.get('tp1') else '—'
        tp2_str = f'{t["tp2"]:.3f}' if t.get('tp2') else '—'
        xp_str  = f'{t["exit_price"]:.3f}' if t.get('exit_price') else '—'

        print(
            f'  {n:<3} {t.get("entry_date","—"):<12} {t.get("exit_date","—"):<12} '
            f'{t["entry_price"]:>8.3f} {xp_str:>8} {t["sl"]:>8.3f} '
            f'{tp1_str:>8} {tp2_str:>8} '
            f'{ret_pct:>+7.1f}%  {rsn} {marker}'
        )

        if win:  win_trades.append(t)
        else:    loss_trades.append(t)

    print(f'  {SEP2}')

    avg_g = sum(t['entry_return_pct'] for t in win_trades)  / len(win_trades)  if win_trades  else 0
    avg_l = sum(t['entry_return_pct'] for t in loss_trades) / len(loss_trades) if loss_trades else 0
    max_g = max((t['entry_return_pct'] for t in win_trades),  default=0)
    max_l = min((t['entry_return_pct'] for t in loss_trades), default=0)

    print(f'  Wins {len(win_trades)}  Losses {len(loss_trades)}  '
          f'Avg gain {avg_g:+.1f}%  Avg loss {avg_l:+.1f}%  '
          f'Max gain {max_g:+.1f}%  Max loss {max_l:+.1f}%')
    print(f'{SEP}\n')