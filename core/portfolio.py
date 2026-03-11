"""
core/portfolio.py — Portfolio backtest with partial TP exits
  Timeline approach: all BUY/SELL events pre-built, sorted, then
  cash replayed in strict date order so values are always correct.
"""

from datetime import date as Date


def simulate_portfolio(results: list, cfg: dict, max_positions: int = 10) -> dict:
    capital    = cfg['capital']
    commission = cfg['commission']

    # ── Collect trades ────────────────────────────────────────────────────
    raw = []
    for r in results:
        for t in r.get('trades', []):
            ed = t.get('entry_date', '')
            xd = t.get('exit_date', '')
            if not ed or 'bar' in str(ed) or not xd or str(xd) == '—':
                continue
            try:
                entry_dt = Date.fromisoformat(str(ed))
                exit_dt  = Date.fromisoformat(str(xd))
            except ValueError:
                continue
            if exit_dt <= entry_dt:
                continue

            tp1_hit  = bool(t.get('tp1_hit', False))
            tp2_hit  = bool(t.get('tp2_hit', False))
            tp1_date = tp2_date = None
            if tp1_hit and t.get('tp1_date'):
                try: tp1_date = Date.fromisoformat(str(t['tp1_date']))
                except: pass
            if tp2_hit and t.get('tp2_date'):
                try: tp2_date = Date.fromisoformat(str(t['tp2_date']))
                except: pass

            raw.append(dict(
                ticker        = r['ticker'],
                ticker_short  = r['ticker'].replace('.BK', ''),
                entry_date    = entry_dt,
                exit_date     = exit_dt,
                tp1_date      = tp1_date,
                tp2_date      = tp2_date,
                tp1_hit       = tp1_hit,
                tp2_hit       = tp2_hit,
                tp1_ret_pct   = float(t.get('tp1_ret_pct',   0)),
                tp2_ret_pct   = float(t.get('tp2_ret_pct',   0)),
                final_ret_pct = float(t.get('final_ret_pct', 0)),
                ret_pct       = float(t.get('ret_pct', 0)),
                win           = bool(t.get('win', False)),
                exit_reason   = t.get('exit_reason', ''),
            ))

    if not raw:
        return None

    raw.sort(key=lambda t: (t['entry_date'], t['ticker_short']))

    # ── Build timeline of pending entries ─────────────────────────────────
    # We process entries one by one in date order.
    # For each entry accepted, we schedule its partial exit events.
    # Timeline item: (date, sort_order, action, ticker, cost_frac, ret_pct, label, trade_ref)

    cash       = float(capital)
    open_pos   = []    # {ticker, cost_total, exits: [(date, frac, ret_pct, label)], tp1_hit, tp2_hit, win}
    raw_events = []    # (date, sort_key, action, ticker, sizing, ret_pct, pnl_raw, label, ticker_full)
    n_skipped  = 0
    closed_stats = []  # for summary

    def flush_exits_before(cutoff_date):
        """Close all partial exits with date < cutoff_date. Returns list of closed exit tuples."""
        nonlocal cash
        still_open = []
        for p in open_pos:
            remaining_exits = []
            for ex in p['exits']:
                ex_date, frac, ret_pct, label = ex
                if ex_date < cutoff_date:
                    cost_slice = p['cost_total'] * frac
                    gross      = cost_slice * (1.0 + ret_pct / 100.0)
                    returned   = gross * (1.0 - commission)
                    pnl        = returned - cost_slice
                    cash      += returned
                    p['cost_remaining'] -= cost_slice
                    tp_suffix = ''
                    if label not in ('TP1', 'TP2'):
                        if p['tp1_hit']: tp_suffix += ' TP1✓'
                        if p['tp2_hit']: tp_suffix += ' TP2✓'
                    raw_events.append((
                        ex_date, 1,       # sort_key 1 = SELL after BUY on same day
                        'SELL', p['ticker_short'], cost_slice, ret_pct, pnl,
                        label + tp_suffix, p['ticker']
                    ))
                    closed_stats.append(dict(ret_pct=ret_pct, pnl=pnl, win=pnl > 0,
                                            label=label, ticker=p['ticker_short']))
                else:
                    remaining_exits.append(ex)
            p['exits'] = remaining_exits
            if remaining_exits:
                still_open.append(p)
        open_pos[:] = still_open

    for t in raw:
        flush_exits_before(t['entry_date'])

        if len(open_pos) >= max_positions:
            n_skipped += 1
            continue

        free_slots = max_positions - len(open_pos)
        slot       = cash / free_slots
        if slot <= 0:
            n_skipped += 1
            continue

        cost  = slot * (1.0 - commission)
        cash -= slot

        # Build exit schedule
        exits = []
        rem   = 1.0
        if t['tp1_hit'] and t['tp1_date']:
            exits.append((t['tp1_date'], 0.30, t['tp1_ret_pct'], 'TP1'))
            rem -= 0.30
        if t['tp2_hit'] and t['tp2_date']:
            exits.append((t['tp2_date'], 0.30, t['tp2_ret_pct'], 'TP2'))
            rem -= 0.30
        rsn = t['exit_reason']
        if rsn == 'EMA10': rsn = 'MA10'
        exits.append((t['exit_date'], rem, t['final_ret_pct'], rsn))

        open_pos.append(dict(
            ticker         = t['ticker'],
            ticker_short   = t['ticker_short'],
            cost_total     = cost,
            cost_remaining = cost,
            exits          = exits,
            tp1_hit        = t['tp1_hit'],
            tp2_hit        = t['tp2_hit'],
            win            = t['win'],
        ))
        raw_events.append((
            t['entry_date'], 0,  # sort_key 0 = BUY before SELL on same day
            'BUY', t['ticker_short'], cost, 0.0, -slot, '', t['ticker']
        ))

    # Flush all remaining positions
    for p in open_pos:
        for ex_date, frac, ret_pct, label in p['exits']:
            cost_slice = p['cost_total'] * frac
            gross      = cost_slice * (1.0 + ret_pct / 100.0)
            returned   = gross * (1.0 - commission)
            pnl        = returned - cost_slice
            cash      += returned
            tp_suffix  = ''
            if label not in ('TP1', 'TP2'):
                if p['tp1_hit']: tp_suffix += ' TP1✓'
                if p['tp2_hit']: tp_suffix += ' TP2✓'
            raw_events.append((
                ex_date, 1, 'SELL', p['ticker_short'], cost_slice, ret_pct, pnl,
                label + tp_suffix, p['ticker']
            ))
            closed_stats.append(dict(ret_pct=ret_pct, pnl=pnl, win=pnl > 0,
                                     label=label, ticker=p['ticker_short']))

    # ── Sort timeline then replay cash ────────────────────────────────────
    raw_events.sort(key=lambda e: (str(e[0]), e[1], e[3]))

    # Replay: recompute running cash and balance from scratch
    replay_cash    = float(capital)
    open_cost_map  = {}   # ticker_short → list of costs currently open
    events         = []

    for ev in raw_events:
        date, _, action, ticker, sizing, ret_pct, pnl, label, ticker_full = ev
        isBuy = action == 'BUY'

        if isBuy:
            replay_cash -= (sizing / (1.0 - commission))  # slot = sizing/(1-commission) ... 
            # Actually sizing = slot*(1-commission), so slot = sizing + commission portion
            # Let's just track: BUY removes slot from cash (pnl = -slot, slot = -pnl)
            replay_cash += pnl   # pnl is negative for BUY (-slot)
            open_cost_map.setdefault(ticker, []).append(sizing)
        else:
            replay_cash += sizing + pnl  # return capital + profit

        # Current open cost = sum of all remaining open positions
        # Approximate: track entries and exits
        if not isBuy and ticker in open_cost_map and open_cost_map[ticker]:
            open_cost_map[ticker].pop(0)  # remove oldest cost for this ticker

        open_total = sum(c for costs in open_cost_map.values() for c in costs)
        balance    = replay_cash + open_total

        events.append(dict(
            date        = str(date),
            action      = action,
            ticker      = ticker,
            ticker_full = ticker_full,
            sizing      = round(sizing),
            cash_after  = round(replay_cash),
            ret_pct     = round(ret_pct, 2),
            pnl         = round(pnl),
            balance     = round(balance),
            accum_pct   = round((balance - capital) / capital * 100, 2),
            reason      = label,
        ))

    # ── Summary ───────────────────────────────────────────────────────────
    final_eq  = round(cash, 2)
    total_ret = round((final_eq - capital) / capital * 100, 2)

    full_trades = raw
    full_wins   = [t for t in raw if t['win']]
    wins_cs     = [c for c in closed_stats if c['pnl'] > 0]
    loss_cs     = [c for c in closed_stats if c['pnl'] <= 0]

    eq_curve = [{'date': str(raw[0]['entry_date']), 'equity': capital}]
    for e in events:
        if e['action'] == 'SELL':
            eq_curve.append({'date': e['date'], 'equity': e['balance']})
    eq_curve.append({'date': str(raw[-1]['exit_date']), 'equity': final_eq})

    peak = capital; max_dd = 0.0
    for pt in eq_curve:
        eq = pt['equity']
        if eq > peak: peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd: max_dd = dd

    win_rets  = [c['ret_pct'] for c in wins_cs]
    loss_rets = [c['ret_pct'] for c in loss_cs]

    return dict(
        start_capital = capital,
        final_equity  = final_eq,
        total_ret_pct = total_ret,
        n_taken       = len(full_trades),
        n_skipped     = n_skipped,
        n_wins        = len(full_wins),
        n_losses      = len(full_trades) - len(full_wins),
        win_rate      = round(len(full_wins) / len(full_trades) * 100, 1) if full_trades else 0,
        avg_win       = round(sum(win_rets)  / len(win_rets),  2) if win_rets  else 0,
        avg_loss      = round(sum(loss_rets) / len(loss_rets), 2) if loss_rets else 0,
        max_drawdown  = round(max_dd, 2),
        max_positions = max_positions,
        equity_curve  = eq_curve,
        events        = events,
    )
