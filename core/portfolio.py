"""
core/portfolio.py — Portfolio backtest with risk-based sizing and partial TP exits.

Sizing: shares = capital × risk_pct ÷ (ATR × sl_mult)
        position_cost = shares × entry_price  (same formula as exit.py)

Balance tracking: each position carries a unique ID; partial exits reduce
cost_remaining by the exact fraction so balance is always correct.
"""

from datetime import date as Date


def simulate_portfolio(results: list, cfg: dict, max_positions: int = 10) -> dict:
    capital    = cfg['capital']
    commission = cfg['commission']
    risk_pct   = cfg['risk_pct']
    sl_mult    = cfg['sl_mult']

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

            # Risk-based position sizing (mirrors exit.py exactly)
            atr_val     = float(t.get('atr_val', 0))
            entry_price = float(t.get('entry_price', 0))
            if atr_val > 0 and entry_price > 0:
                sld    = atr_val * sl_mult
                shares = max(1, int((capital * risk_pct) / sld))
                cost   = shares * entry_price   # gross cost before commission
            else:
                cost = capital / max_positions  # fallback

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
                cost          = cost,           # position size in ฿
                atr_val       = atr_val,
                entry_price   = entry_price,
            ))

    if not raw:
        return None

    raw.sort(key=lambda t: (t['entry_date'], t['ticker_short']))

    # ── Simulate ──────────────────────────────────────────────────────────
    cash       = float(capital)
    open_pos   = {}     # pos_id → position dict
    pos_seq    = 0      # unique ID counter
    raw_events = []
    n_skipped  = 0
    closed_stats = []

    def flush_exits_before(cutoff_date):
        nonlocal cash
        to_remove = []
        for pid, p in open_pos.items():
            done = []
            keep = []
            for ex in p['exits']:
                ex_date, frac, ret_pct, label = ex
                if ex_date < cutoff_date:
                    slice_cost = p['cost_total'] * frac
                    gross      = slice_cost * (1.0 + ret_pct / 100.0)
                    returned   = gross * (1.0 - commission)
                    pnl        = returned - slice_cost
                    cash      += returned
                    p['cost_remaining'] -= slice_cost
                    done.append((ex_date, frac, ret_pct, label, slice_cost, pnl))
                    closed_stats.append(dict(ret_pct=ret_pct, pnl=pnl, win=pnl > 0))
                else:
                    keep.append(ex)
            for ex_date, frac, ret_pct, label, slice_cost, pnl in done:
                tp_suffix = ''
                if label not in ('TP1', 'TP2'):
                    if p['tp1_hit']: tp_suffix += ' TP1✓'
                    if p['tp2_hit']: tp_suffix += ' TP2✓'
                raw_events.append((
                    ex_date, 1, 'SELL', p['ticker_short'],
                    slice_cost, ret_pct, pnl, label + tp_suffix, p['ticker']
                ))
            p['exits'] = keep
            if not keep:
                to_remove.append(pid)
        for pid in to_remove:
            del open_pos[pid]

    for t in raw:
        flush_exits_before(t['entry_date'])

        if len(open_pos) >= max_positions:
            n_skipped += 1
            continue
        if t['cost'] > cash:
            n_skipped += 1
            continue

        # Deduct with commission
        actual_cost = t['cost'] * (1.0 + commission)
        cash -= actual_cost

        # Build partial exit schedule
        exits = []
        rem = 1.0
        if t['tp1_hit'] and t['tp1_date']:
            exits.append((t['tp1_date'], 0.30, t['tp1_ret_pct'], 'TP1'))
            rem -= 0.30
        if t['tp2_hit'] and t['tp2_date']:
            exits.append((t['tp2_date'], 0.30, t['tp2_ret_pct'], 'TP2'))
            rem -= 0.30
        rsn = t['exit_reason']
        if rsn == 'EMA10': rsn = 'MA10'
        exits.append((t['exit_date'], rem, t['final_ret_pct'], rsn))

        pos_seq += 1
        open_pos[pos_seq] = dict(
            ticker         = t['ticker'],
            ticker_short   = t['ticker_short'],
            cost_total     = t['cost'],
            cost_remaining = t['cost'],
            exits          = exits,
            tp1_hit        = t['tp1_hit'],
            tp2_hit        = t['tp2_hit'],
            win            = t['win'],
            exit_reason    = rsn,
        )
        raw_events.append((
            t['entry_date'], 0, 'BUY', t['ticker_short'],
            t['cost'], 0.0, -actual_cost, '', t['ticker']
        ))

    # ── Flush all remaining positions after main loop ─────────────────────
    # Most of these have real exits (SL/MA10) — they just had no later trade to
    # trigger flush_exits_before(). Only exit_reason='End' means genuinely open.
    for pid, p in open_pos.items():
        for ex_date, frac, ret_pct, label in p['exits']:
            slice_cost = p['cost_total'] * frac
            is_end     = p['exit_reason'] == 'End'

            if is_end:
                # Genuinely still holding at end of data
                raw_events.append((
                    ex_date, 2, 'OPEN', p['ticker_short'],
                    slice_cost, 0.0, 0.0, 'Still holding', p['ticker']
                ))
            else:
                # Real exit that just wasn't flushed yet
                gross    = slice_cost * (1.0 + ret_pct / 100.0)
                returned = gross * (1.0 - commission)
                pnl      = returned - slice_cost
                cash    += returned
                tp_suffix = ''
                if p['tp1_hit']: tp_suffix += ' TP1✓'
                if p['tp2_hit']: tp_suffix += ' TP2✓'
                raw_events.append((
                    ex_date, 1, 'SELL', p['ticker_short'],
                    slice_cost, ret_pct, pnl, label + tp_suffix, p['ticker']
                ))
                closed_stats.append(dict(ret_pct=ret_pct, pnl=pnl, win=pnl > 0))

    # ── Replay cash in strict date order ──────────────────────────────────
    raw_events.sort(key=lambda e: (str(e[0]), e[1], e[3]))

    # Track open cost per position using a running dict: ticker → [cost_remaining_slices]
    # Use a simpler approach: maintain total_open_cost updated at each event
    replay_cash      = float(capital)
    total_open_cost  = 0.0   # sum of all remaining position costs
    events           = []

    for ev in raw_events:
        date, _, action, ticker, sizing, ret_pct, pnl, label, ticker_full = ev

        if action == 'BUY':
            replay_cash    -= (sizing * (1.0 + commission))
            total_open_cost += sizing
        elif action == 'SELL':
            replay_cash    += sizing * (1.0 + ret_pct / 100.0) * (1.0 - commission)
            total_open_cost -= sizing
        # OPEN: no change

        balance = replay_cash + total_open_cost

        events.append(dict(
            date        = str(date),
            action      = action,
            ticker      = ticker,
            ticker_full = ticker_full,
            sizing      = round(sizing),
            cash_after  = round(replay_cash),
            ret_pct     = round(ret_pct, 2),
            pnl         = round(pnl) if action == 'SELL' else 0,
            balance     = round(balance),
            reason      = label,
        ))

    # ── Summary ───────────────────────────────────────────────────────────
    # Final cash from actual simulation (not replay — replay accumulates float drift)
    # Flush remaining for final equity calculation
    final_cash = cash
    for pid, p in open_pos.items():
        for ex_date, frac, ret_pct, label in p['exits']:
            slice_cost  = p['cost_total'] * frac
            returned    = slice_cost * (1.0 + ret_pct / 100.0) * (1.0 - commission)
            final_cash += returned

    final_eq  = round(final_cash, 2)
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
