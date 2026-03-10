"""
exit.py — Trade simulation (money management)
  simulate(df, signal_bars, cfg)
      -> (trades, buys, sells)

Money management rules
  ─────────────────────────────────────────────────────────
  Entry     : fill AT break price (same bar close crosses level)
  SL        : entry - 1x ATR  (sl_mult from cfg)
  Breakeven : after be_days bars move SL to entry price
  TP1       : entry + 2x ATR  → exit 30 pct of position  (tp1_mult)
  TP2       : entry + 4x ATR  → exit 30 pct of position  (tp2_mult)
  Final     : remaining 40 pct exits when Close < EMA10
  End       : still open at last bar — exit at close
  Commission: per-side rate applied on every fill

  Multiple positions: all signals enter independently, each managed
  with its own SL/TP/breakeven. No limit on concurrent positions.
  Position sizing uses capital / risk_pct per trade (fixed).
  ─────────────────────────────────────────────────────────

Each trade dict keys
  entry_bar, signal_bar, entry_price, entry_level
  shares, shares_remaining
  sl, tp1, tp2
  atr_val, rsm_at_entry
  tp1_hit, tp1_bar, tp2_hit, tp2_bar
  realized_pnl, total_pnl, pnl_pct
  exit_bar, exit_price, exit_reason  ('SL' | 'EMA10' | 'End')
"""

import numpy as np
import pandas as pd


def simulate(
    df:           pd.DataFrame,
    signal_bars:  list,          # list of (bar_index, break_price) from entry.py
    cfg:          dict,
) -> tuple[list, list, list]:
    capital    = cfg['capital']
    risk_pct   = cfg['risk_pct']
    commission = cfg['commission']
    sl_mult    = cfg['sl_mult']
    tp1_mult   = cfg['tp1_mult']
    tp2_mult   = cfg['tp2_mult']
    be_days    = cfg['be_days']

    N      = len(df)
    sigs   = {bar: bp for bar, bp in signal_bars}
    trades = []
    buys   = []
    sells  = []
    open_positions = []   # list of active trade dicts (multiple allowed)

    for i in range(N):
        ci      = float(df['Close'].iloc[i])
        lo      = float(df['Low'].iloc[i])
        e10     = float(df['EMA10'].iloc[i])
        atr_raw = df['ATR'].iloc[i]
        atr     = float(atr_raw) if not pd.isna(atr_raw) else 0.0

        # ── Manage all open positions ──────────────────────────────────────
        still_open = []
        for pos in open_positions:
            days = i - pos['entry_bar']

            # Breakeven
            if days == be_days:
                pos['sl'] = pos['entry_price']

            # TP1
            if not pos['tp1_hit'] and ci >= pos['tp1']:
                sh = pos['shares'] * 0.30
                pos['realized_pnl'] += ((pos['tp1'] - pos['entry_price']) * sh
                                        - pos['tp1'] * sh * commission)
                pos['shares_remaining'] = pos['shares'] * 0.70
                pos['tp1_hit'] = True
                pos['tp1_bar'] = i

            # TP2
            if pos['tp1_hit'] and not pos['tp2_hit'] and ci >= pos['tp2']:
                frac = 0.30 / 0.70
                sh   = pos['shares_remaining'] * frac
                pos['realized_pnl'] += ((pos['tp2'] - pos['entry_price']) * sh
                                        - pos['tp2'] * sh * commission)
                pos['shares_remaining'] *= (1 - frac)
                pos['tp2_hit'] = True
                pos['tp2_bar'] = i

            # Exit triggers
            sl_hit   = lo <= pos['sl']
            ema_exit = ci < e10

            if sl_hit or ema_exit:
                ep  = pos['sl'] if sl_hit else ci
                rsn = 'SL' if sl_hit else 'EMA10'
                pos['realized_pnl'] += ((ep - pos['entry_price']) * pos['shares_remaining']
                                        - ep * pos['shares_remaining'] * commission)
                pos.update(exit_bar=i, exit_price=ep, exit_reason=rsn,
                           total_pnl=pos['realized_pnl'])
                pos['pnl_pct'] = pos['total_pnl'] / capital * 100
                trades.append(pos)
                sells.append((i, rsn))
            else:
                still_open.append(pos)

        open_positions = still_open

        # ── New entry (always allowed — multiple positions OK) ─────────────
        if i in sigs and atr > 0:
            bp  = sigs[i]
            ep  = bp
            sld = atr * sl_mult
            sh  = max(1, int((capital * risk_pct) / sld))
            rsm_val = df['RSM'].iloc[i]
            pos = dict(
                entry_bar=i, signal_bar=i, entry_price=ep, entry_level=bp,
                shares=sh, shares_remaining=sh,
                sl=ep - sld,
                tp1=ep + tp1_mult * sld,
                tp2=ep + tp2_mult * sld,
                atr_val=atr,
                rsm_at_entry=round(float(rsm_val) if not pd.isna(rsm_val) else 0, 1),
                tp1_hit=False, tp2_hit=False, tp1_bar=None, tp2_bar=None,
                realized_pnl=-(ep * sh * commission),   # entry commission
                total_pnl=0.0, pnl_pct=0.0,
                exit_bar=None, exit_price=None, exit_reason='Open',
            )
            open_positions.append(pos)
            buys.append(i)

    # ── Close all still-open positions at last bar ────────────────────────
    ep = float(df['Close'].iloc[-1])
    for pos in open_positions:
        pos['realized_pnl'] += ((ep - pos['entry_price']) * pos['shares_remaining']
                                - ep * pos['shares_remaining'] * commission)
        pos.update(exit_bar=N - 1, exit_price=ep, exit_reason='End',
                   total_pnl=pos['realized_pnl'])
        pos['pnl_pct'] = pos['total_pnl'] / capital * 100
        trades.append(pos)
        sells.append((N - 1, 'End'))

    trades.sort(key=lambda t: t['entry_bar'])
    return trades, buys, sells