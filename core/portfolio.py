"""
core/portfolio.py — Portfolio backtest with partial TP exits
  Each trade splits into up to 3 SELL events:
    TP1  — 30% on tp1_date   (if tp1_hit)
    TP2  — 30% on tp2_date   (if tp2_hit)
    FINAL— remaining on exit_date  (MA10 / SL / End)
  Cash is freed up at each partial exit.
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
            tp1_date = None
            tp2_date = None
            if tp1_hit and t.get('tp1_date'):
                try:    tp1_date = Date.fromisoformat(str(t['tp1_date']))
                except: pass
            if tp2_hit and t.get('tp2_date'):
                try:    tp2_date = Date.fromisoformat(str(t['tp2_date']))
                except: pass

            raw.append(dict(
                ticker        = r['ticker'].replace('.BK', ''),
                entry_date    = entry_dt,
                exit_date     = exit_dt,
                tp1_date      = tp1_date,
                tp2_date      = tp2_date,
                tp1_hit       = tp1_hit,
                tp2_hit       = tp2_hit,
                tp1_ret_pct   = float(t.get('tp1_ret_pct',   0)),
                tp2_ret_pct   = float(t.get('tp2_ret_pct',   0)),
                final_ret_pct = float(t.get('final_ret_pct', 0)),
                ret_pct       = float(t.get('ret_pct', 0)),   # blended (for win/loss)
                win           = bool(t.get('win', False)),
                exit_reason   = t.get('exit_reason', ''),
            ))

    if not raw:
        return None

    raw.sort(key=lambda t: (t['entry_date'], t['ticker']))

    # ── Build exit events per trade ───────────────────────────────────────
    # Each trade becomes a list of partial exits with (date, frac, ret_pct, label)
    def build_exits(t):
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
        return exits

    # ── Simulate ──────────────────────────────────────────────────────────
    cash      = float(capital)
    open_pos  = []   # each: {ticker, entry_date, cost_total, exits_remaining, win}
    closed    = []   # completed partial exits for stats
    events    = []
    n_skipped = 0

    def current_equity():
        return cash + sum(p['cost_remaining'] for p in open_pos)

    def add_event(date, action, ticker, sizing, ret_pct, pnl, reason):
        events.append(dict(
            date       = str(date),
            action     = action,
            ticker     = ticker,
            sizing     = round(sizing),
            cash_after = round(cash),
            ret_pct    = round(ret_pct, 2),
            pnl        = round(pnl),
            balance    = round(current_equity()),
            reason     = reason,
        ))

    # Collect all events (entry + partial exits) into a timeline
    # We process day by day in entry order, flushing exits as we go

    for t in raw:

        # 1. Flush any exits due on or before this entry date
        still_open = []
        for p in open_pos:
            flushed = []
            kept    = []
            for ex in p['exits']:
                ex_date, frac, ret_pct, label = ex
                if ex_date <= t['entry_date']:
                    cost_slice = p['cost_total'] * frac
                    gross      = cost_slice * (1.0 + ret_pct / 100.0)
                    returned   = gross * (1.0 - commission)
                    pnl        = returned - cost_slice
                    cash      += returned
                    p['cost_remaining'] -= cost_slice
                    flushed.append((ex_date, frac, ret_pct, label, cost_slice, pnl))
                    closed.append(dict(ticker=p['ticker'], ret_pct=ret_pct,
                                       pnl=pnl, win=pnl > 0, label=label))
                else:
                    kept.append(ex)
            for ex_date, frac, ret_pct, label, cost_slice, pnl in flushed:
                tps = ' '.join(filter(None,[
                    'TP1✓' if p.get('tp1_hit') else '',
                    'TP2✓' if p.get('tp2_hit') else '',
                ]))
                full_label = label
                if label not in ('TP1','TP2'):
                    full_label = label + (' TP1✓' if p.get('tp1_hit') else '') + (' TP2✓' if p.get('tp2_hit') else '')
                add_event(ex_date, 'SELL', p['ticker'],
                          cost_slice, ret_pct, pnl, full_label.strip())
            p['exits'] = kept
            if kept:
                still_open.append(p)
        open_pos = still_open

        # 2. Skip if at max
        if len(open_pos) >= max_positions:
            n_skipped += 1
            continue

        # 3. Open position
        free_slots = max_positions - len(open_pos)
        slot       = cash / free_slots
        if slot <= 0:
            n_skipped += 1
            continue

        cost  = slot * (1.0 - commission)
        cash -= slot

        exits = build_exits(t)
        pos   = dict(
            ticker         = t['ticker'],
            entry_date     = t['entry_date'],
            cost_total     = cost,
            cost_remaining = cost,
            exits          = exits,
            tp1_hit        = t['tp1_hit'],
            tp2_hit        = t['tp2_hit'],
            win            = t['win'],
        )
        open_pos.append(pos)
        add_event(t['entry_date'], 'BUY', t['ticker'], cost, 0, -slot, '')

    # 4. Force-close remaining
    for p in open_pos:
        for ex_date, frac, ret_pct, label in p['exits']:
            cost_slice = p['cost_total'] * frac
            gross      = cost_slice * (1.0 + ret_pct / 100.0)
            returned   = gross * (1.0 - commission)
            pnl        = returned - cost_slice
            cash      += returned
            p['cost_remaining'] -= cost_slice
            closed.append(dict(ticker=p['ticker'], ret_pct=ret_pct,
                               pnl=pnl, win=pnl > 0, label=label))
            if label not in ('TP1','TP2'):
                label = label + (' TP1✓' if p.get('tp1_hit') else '') + (' TP2✓' if p.get('tp2_hit') else '')
            add_event(ex_date, 'SELL', p['ticker'], cost_slice, ret_pct, pnl, label.strip())

    events.sort(key=lambda e: (e['date'], 0 if e['action']=='BUY' else 1))

    # ── Summary ───────────────────────────────────────────────────────────
    wins   = [c for c in closed if c['pnl'] > 0]
    losses = [c for c in closed if c['pnl'] <= 0]
    # Count full trades (not partials) for win rate
    full_trades = [t for t in raw if t['entry_date'] is not None]
    full_wins   = [t for t in full_trades if t['win']]

    final_eq  = round(cash, 2)
    total_ret = round((final_eq - capital) / capital * 100, 2)

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

    win_rets  = [c['ret_pct'] for c in closed if c['pnl'] > 0]
    loss_rets = [c['ret_pct'] for c in closed if c['pnl'] <= 0]

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
