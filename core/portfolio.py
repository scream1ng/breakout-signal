"""
core/portfolio.py — Portfolio-level backtest with day-by-day event log
  simulate_portfolio(results, cfg, max_positions) -> dict

  Runs all trades in strict calendar order, shared cash pool.
  Generates a chronological event log: BUY / SELL / TP with running balance.
"""

from datetime import date as Date


def simulate_portfolio(results: list, cfg: dict, max_positions: int = 10) -> dict:
    capital    = cfg['capital']
    commission = cfg['commission']

    # ── Collect trades with valid dates ───────────────────────────────────
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
            raw.append(dict(
                ticker      = r['ticker'].replace('.BK', ''),
                entry_date  = entry_dt,
                exit_date   = exit_dt,
                ret_pct     = float(t.get('ret_pct', 0.0)),
                win         = bool(t.get('win', False)),
                exit_reason = t.get('exit_reason', ''),
                tp1_hit     = bool(t.get('tp1_hit', False)),
                tp2_hit     = bool(t.get('tp2_hit', False)),
            ))

    if not raw:
        return None

    raw.sort(key=lambda t: (t['entry_date'], t['ticker']))

    # ── Simulate ──────────────────────────────────────────────────────────
    cash      = float(capital)
    open_pos  = []   # active positions (cash deducted)
    closed    = []
    events    = []   # day-by-day log
    n_skipped = 0

    def current_equity():
        return cash + sum(p['cost'] for p in open_pos)

    def add_event(date, action, ticker, ret_pct, pnl, reason=''):
        events.append(dict(
            date     = str(date),
            action   = action,       # BUY | SELL | TP1 | TP2
            ticker   = ticker,
            ret_pct  = round(ret_pct, 2),
            pnl      = round(pnl, 2),
            balance  = round(current_equity(), 2),
            reason   = reason,
        ))

    for t in raw:
        # 1. Close positions exiting on or before this entry date
        remaining = []
        for p in open_pos:
            if p['exit_date'] <= t['entry_date']:
                gross    = p['cost'] * (1.0 + p['ret_pct'] / 100.0)
                exit_val = gross * (1.0 - commission)
                pnl      = exit_val - p['cost']
                cash    += exit_val
                p['port_pnl'] = round(pnl, 2)
                p['win']      = t['win']
                closed.append(p)
                reason = p['exit_reason']
                if reason == 'EMA10': reason = 'MA10'
                tps = ' '.join(filter(None, [
                    'TP1✓' if p.get('tp1_hit') else '',
                    'TP2✓' if p.get('tp2_hit') else '',
                ]))
                add_event(p['exit_date'], 'SELL', p['ticker'],
                          p['ret_pct'], pnl, f"{reason} {tps}".strip())
            else:
                remaining.append(p)
        open_pos = remaining

        # 2. Skip if at capacity
        if len(open_pos) >= max_positions:
            n_skipped += 1
            continue

        # 3. Open new position
        free_slots = max_positions - len(open_pos)
        slot       = cash / free_slots
        if slot <= 0:
            n_skipped += 1
            continue

        cost  = slot * (1.0 - commission)
        cash -= slot

        pos = dict(
            ticker      = t['ticker'],
            entry_date  = t['entry_date'],
            exit_date   = t['exit_date'],
            ret_pct     = t['ret_pct'],
            win         = t['win'],
            exit_reason = t['exit_reason'],
            tp1_hit     = t['tp1_hit'],
            tp2_hit     = t['tp2_hit'],
            cost        = cost,
            port_pnl    = 0.0,
        )
        open_pos.append(pos)
        add_event(t['entry_date'], 'BUY', t['ticker'], 0, -slot, '')

    # 4. Force-close remaining
    for p in open_pos:
        gross    = p['cost'] * (1.0 + p['ret_pct'] / 100.0)
        exit_val = gross * (1.0 - commission)
        pnl      = exit_val - p['cost']
        cash    += exit_val
        p['port_pnl'] = round(pnl, 2)
        closed.append(p)
        reason = p['exit_reason']
        if reason == 'EMA10': reason = 'MA10'
        tps = ' '.join(filter(None, [
            'TP1✓' if p.get('tp1_hit') else '',
            'TP2✓' if p.get('tp2_hit') else '',
        ]))
        add_event(p['exit_date'], 'SELL', p['ticker'],
                  p['ret_pct'], pnl, f"{reason} {tps}".strip())

    # Sort events chronologically
    events.sort(key=lambda e: (e['date'], e['action']))

    # Recompute running balance on sorted events
    cash2     = float(capital)
    open_cost = {}   # ticker→cost for tracking
    open_pos2 = []
    # Re-derive balance from event sequence
    balance = float(capital)
    buy_costs = {}   # idx→cost for partial tracking
    # Simpler: just re-walk events and recompute balance
    # We already have correct final balance; tag each event with its running balance
    # Since events were recorded with current_equity() at time of event,
    # they're already correct. Just keep them.

    # ── Summary ───────────────────────────────────────────────────────────
    wins   = [p for p in closed if p.get('port_pnl', 0) > 0]
    losses = [p for p in closed if p.get('port_pnl', 0) <= 0]

    final_eq  = round(cash, 2)
    total_ret = round((final_eq - capital) / capital * 100, 2)

    # Equity curve from SELL events only (cleaner)
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

    all_rets  = [p['ret_pct'] for p in closed]
    win_rets  = [p['ret_pct'] for p in wins]
    loss_rets = [p['ret_pct'] for p in losses]

    return dict(
        start_capital = capital,
        final_equity  = final_eq,
        total_ret_pct = total_ret,
        n_taken       = len(closed),
        n_skipped     = n_skipped,
        n_wins        = len(wins),
        n_losses      = len(losses),
        win_rate      = round(len(wins) / len(closed) * 100, 1) if closed else 0,
        avg_win       = round(sum(win_rets)  / len(win_rets),  2) if win_rets  else 0,
        avg_loss      = round(sum(loss_rets) / len(loss_rets), 2) if loss_rets else 0,
        max_drawdown  = round(max_dd, 2),
        max_positions = max_positions,
        equity_curve  = eq_curve,
        events        = events,   # day-by-day BUY/SELL log
    )
