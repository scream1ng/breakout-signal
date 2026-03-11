"""
exit.py — Trade simulation (money management)
  simulate(df, signal_bars, cfg) -> (trades, buys, sells)

Entry    : break price + 1 SET tick
SL       : entry − 1×ATR  → exit at close when close ≤ SL
Breakeven: after be_days bars SL moves to entry → exit at close
TP1      : entry + 2×ATR  → exit 30%  (limit order, fills at TP1)
TP2      : entry + 4×ATR  → exit 30%  (limit order, fills at TP2)
Final    : remaining 40% exits when close < EMA10 → exit at close
End      : still open at last bar → exit at close
Commission: per-side on every fill
"""

import numpy as np
import pandas as pd


def set_tick(price: float) -> float:
    """Thai SET tick size by price range."""
    if   price <   2: return 0.01
    elif price <   5: return 0.02
    elif price <  10: return 0.05
    elif price <  25: return 0.10
    elif price < 100: return 0.25
    elif price < 200: return 0.50
    elif price < 400: return 1.00
    else:             return 2.00


def simulate(df, signal_bars, cfg):
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
    open_positions = []

    for i in range(N):
        ci      = float(df['Close'].iloc[i])
        e10     = float(df['EMA10'].iloc[i])
        atr_raw = df['ATR'].iloc[i]
        atr     = float(atr_raw) if not pd.isna(atr_raw) else 0.0

        # ── Manage open positions ─────────────────────────────────────────
        still_open = []
        for pos in open_positions:
            days = i - pos['entry_bar']

            # Breakeven
            if days == be_days:
                pos['sl'] = pos['entry_price']

            # TP1 — limit order, fills at TP1 level
            if not pos['tp1_hit'] and ci >= pos['tp1']:
                sh = pos['shares'] * 0.30
                pos['realized_pnl'] += ((pos['tp1'] - pos['entry_price']) * sh
                                        - pos['tp1'] * sh * commission)
                pos['shares_remaining'] = pos['shares'] * 0.70
                pos['tp1_hit'] = True
                pos['tp1_bar'] = i

            # TP2 — limit order, fills at TP2 level
            if pos['tp1_hit'] and not pos['tp2_hit'] and ci >= pos['tp2']:
                frac = 0.30 / 0.70
                sh   = pos['shares_remaining'] * frac
                pos['realized_pnl'] += ((pos['tp2'] - pos['entry_price']) * sh
                                        - pos['tp2'] * sh * commission)
                pos['shares_remaining'] *= (1 - frac)
                pos['tp2_hit'] = True
                pos['tp2_bar'] = i

            # Exit at close: SL or EMA10
            sl_hit   = ci <= pos['sl']
            ema_exit = ci < e10

            if sl_hit or ema_exit:
                rsn = 'SL' if sl_hit else 'EMA10'
                ep  = ci   # always exit at close
                pos['realized_pnl'] += ((ep - pos['entry_price']) * pos['shares_remaining']
                                        - ep * pos['shares_remaining'] * commission)
                pos.update(exit_bar=i, exit_price=ep, exit_reason=rsn,
                           total_pnl=pos['realized_pnl'])
                pos['pnl_pct']          = pos['total_pnl'] / capital * 100
                invested                = pos['entry_price'] * pos['shares']
                pos['entry_return_pct'] = pos['total_pnl'] / invested * 100 if invested else 0
                pos['win']              = pos['total_pnl'] > 0
                pos['ret_pct']          = pos['entry_return_pct']
                trades.append(pos)
                sells.append((i, rsn))
            else:
                still_open.append(pos)

        open_positions = still_open

        # ── New entry: max(break price + 1 tick, open) to handle gap-ups ──
        if i in sigs and atr > 0:
            bp       = sigs[i]
            tick_ep  = round(bp + set_tick(bp), 6)
            open_i   = float(df['Open'].iloc[i])
            ep       = max(tick_ep, open_i)          # gap-up fills at open
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
                realized_pnl=-(ep * sh * commission),
                total_pnl=0.0, pnl_pct=0.0,
                win=False, ret_pct=0.0,
                exit_bar=None, exit_price=None, exit_reason='Open',
            )
            open_positions.append(pos)
            buys.append(i)

    # ── Close all still-open at last bar ─────────────────────────────────
    ep = float(df['Close'].iloc[-1])
    for pos in open_positions:
        pos['realized_pnl'] += ((ep - pos['entry_price']) * pos['shares_remaining']
                                - ep * pos['shares_remaining'] * commission)
        pos.update(exit_bar=N - 1, exit_price=ep, exit_reason='End',
                   total_pnl=pos['realized_pnl'])
        pos['pnl_pct']          = pos['total_pnl'] / capital * 100
        invested                = pos['entry_price'] * pos['shares']
        pos['entry_return_pct'] = pos['total_pnl'] / invested * 100 if invested else 0
        pos['win']              = pos['total_pnl'] > 0
        pos['ret_pct']          = pos['entry_return_pct']
        trades.append(pos)
        sells.append((N - 1, 'End'))

    trades.sort(key=lambda t: t['entry_bar'])
    return trades, buys, sells
