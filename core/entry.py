"""
entry.py — Pivot Breakout signal detection
  detect_pivots(df, psth_val, rvol_arr, cfg, ticker)
      -> (all_breaks, hz_lines, tl_lines)

  all_breaks : list of dicts — every possible break, NO filters applied
               keys: bar, bp, kind ('hz'|'tl'), date,
                     rsm, rvol, atr, close, sma50,
                     rsm_ok, rvol_ok, regime_ok
  hz_lines   : list of (xs, ys)
  tl_lines   : list of (xs, ys)

Line termination
  Lines terminate when close is STRICTLY above them (cl > level).
  Close exactly AT the level keeps the line alive.
  Lines also die when close < SMA50 (regime lost).

Pivot detection regime
  Pivot highs are only registered when they are above SMA50.
  Up to SHAKEOUT_BARS (3) consecutive closes below SMA50 are forgiven
  when building trendlines — prevents stale lines across deep pullbacks.
"""

import numpy as np
import pandas as pd


SHAKEOUT_BARS = 3


def detect_pivots(
    df:        pd.DataFrame,
    psth_val:  int,
    rvol_arr:  np.ndarray,
    cfg:       dict,
    ticker:    str = '',
) -> tuple[list, list, list]:
    """
    Returns ALL possible breaks with full metadata — no filters.
    Caller decides which to simulate and which to display.
    """
    rsm_min  = cfg['rsm_min']
    rvol_min = cfg['rvol_min']
    N        = len(df)

    all_breaks = []
    hz_lines   = []
    tl_lines   = []

    hz_xs = []; hz_ys = []; hz_active = False
    tl_xs = []; tl_ys = []; tl_active = False
    ph0_v = np.nan; ph0_i = -1
    ph1_v = np.nan; ph1_i = -1
    tl_slope = np.nan; tl_base = np.nan; tl_base_i = -1
    in_regime  = False
    bars_below = 0

    def save_hz():
        if hz_active and len(hz_xs) >= 2:
            hz_lines.append((list(hz_xs), list(hz_ys)))

    def save_tl():
        if tl_active and len(tl_xs) >= 2:
            tl_lines.append((list(tl_xs), list(tl_ys)))

    for i in range(psth_val, N):
        cl_i      = float(df['Close'].iloc[i])
        hi_i      = float(df['High'].iloc[i])
        sma_i_raw = df['SMA50'].iloc[i]
        sma_i     = float(sma_i_raw) if not pd.isna(sma_i_raw) else np.nan

        # ── Regime tracking ───────────────────────────────────────────────
        if np.isnan(sma_i) or cl_i <= sma_i:
            bars_below += 1
        else:
            bars_below = 0

        prev_in_regime = in_regime
        in_regime = bars_below < SHAKEOUT_BARS

        if prev_in_regime and not in_regime:
            save_hz(); hz_xs = []; hz_ys = []; hz_active = False
            save_tl(); tl_xs = []; tl_ys = []; tl_active = False
            ph0_v = np.nan; ph0_i = -1
            ph1_v = np.nan; ph1_i = -1
            tl_slope = np.nan; tl_base = np.nan; tl_base_i = -1

        # ── Pivot high confirmation ────────────────────────────────────────
        if i >= 2 * psth_val:
            ph_bar = i - psth_val
            ph_hi  = float(df['High'].iloc[ph_bar])
            win    = df['High'].iloc[ph_bar - psth_val : ph_bar + psth_val + 1].values
            if len(win) == 2 * psth_val + 1 and ph_hi == win.max():
                ph_sma_raw = df['SMA50'].iloc[ph_bar]
                ph_sma = float(ph_sma_raw) if not pd.isna(ph_sma_raw) else np.nan
                if not np.isnan(ph_sma) and ph_hi > ph_sma:
                    save_hz()
                    hz_xs = [ph_bar]; hz_ys = [ph_hi]; hz_active = True
                    ph1_v = ph0_v; ph1_i = ph0_i
                    ph0_v = ph_hi; ph0_i = ph_bar

                    if not np.isnan(ph1_v) and ph0_v < ph1_v and ph1_i >= 0:
                        cl_sl  = df['Close'].iloc[ph1_i:ph0_i + 1].values
                        sma_sl = df['SMA50'].iloc[ph1_i:ph0_i + 1].values
                        max_consec = 0; consec = 0
                        for c, s in zip(cl_sl, sma_sl):
                            if not np.isnan(s) and c < s:
                                consec += 1; max_consec = max(max_consec, consec)
                            else:
                                consec = 0
                        if max_consec < SHAKEOUT_BARS:
                            save_tl()
                            tl_slope  = (ph0_v - ph1_v) / (ph0_i - ph1_i)
                            tl_base   = ph0_v
                            tl_base_i = ph0_i
                            tl_xs     = [ph1_i, ph0_i]
                            tl_ys     = [ph1_v, ph0_v]
                            tl_active = True

        # ── Current level values ──────────────────────────────────────────
        tl_val   = (tl_base + tl_slope * (i - tl_base_i)
                    if not np.isnan(tl_slope) and tl_base_i >= 0 and tl_active else np.nan)
        hz_level = ph0_v if hz_active and not np.isnan(ph0_v) else np.nan
        tl_level = tl_val if tl_active and not np.isnan(tl_val) else np.nan

        # ── Signal fires BEFORE line terminates ──────────────────────────
        # Must check signal here while hz_active/tl_active are still True.
        # If we terminated the line first, hz_active would be False and
        # the signal check would never fire.
        prev_cl = float(df['Close'].iloc[i - 1]) if i > 0 else np.nan

        hz_break = (hz_active and not np.isnan(hz_level)
                    and cl_i > hz_level       # close strictly above
                    and prev_cl <= hz_level)   # was at or below yesterday

        tl_break = (tl_active and not np.isnan(tl_level)
                    and cl_i > tl_level
                    and prev_cl <= tl_level)

        if hz_break or tl_break:
            bp   = hz_level if hz_break else tl_level
            kind = 'hz'    if hz_break else 'tl'

            atr_raw = df['ATR'].iloc[i] if 'ATR' in df.columns else np.nan
            atr     = float(atr_raw) if not pd.isna(atr_raw) else 0.0
            rsm_raw = df['RSM'].iloc[i] if 'RSM' in df.columns else np.nan
            rsm_val = float(rsm_raw) if not pd.isna(rsm_raw) else 0.0
            rv      = float(rvol_arr[i])
            date_str = (str(df.index[i].date())
                        if hasattr(df.index[i], 'date') else str(i))

            atr_pct_val = (atr / bp * 100) if bp > 0 else 0
            price_dist  = ((bp - sma_i) / sma_i * 100) if (not np.isnan(sma_i) and sma_i > 0) else 0
            stretch_val = round(price_dist / atr_pct_val, 2) if atr_pct_val > 0 else 0
            import math as _math
            tl_angle = round(abs(_math.degrees(_math.atan(tl_slope))), 1) \
                       if kind == 'tl' and not np.isnan(tl_slope) else None
            all_breaks.append(dict(
                bar       = i,
                bp        = bp,
                kind      = kind,
                date      = date_str,
                rsm       = round(rsm_val, 1),
                rvol      = round(rv, 2),
                atr       = round(atr, 4),
                close     = round(cl_i, 4),
                sma50     = round(sma_i, 4) if not np.isnan(sma_i) else None,
                stretch   = stretch_val,
                tl_angle  = tl_angle,
                rsm_ok    = rsm_val >= rsm_min,
                rvol_ok   = rv >= rvol_min,
                regime_ok = in_regime and (not np.isnan(sma_i)) and (cl_i > sma_i),
            ))

        # ── Line termination: close STRICTLY above level ──────────────────
        # Runs AFTER signal check. Wick above + close below = line stays alive.
        hz_closed_above = hz_active and not np.isnan(hz_level) and cl_i > hz_level
        tl_closed_above = tl_active and not np.isnan(tl_level) and cl_i > tl_level

        if hz_closed_above:
            hz_xs.append(i); hz_ys.append(hz_level)
            save_hz(); hz_xs = []; hz_ys = []; hz_active = False
        elif hz_active and not np.isnan(sma_i) and cl_i < sma_i:
            hz_xs.append(i); hz_ys.append(hz_level)
            save_hz(); hz_xs = []; hz_ys = []; hz_active = False
        elif hz_active:
            hz_xs.append(i); hz_ys.append(hz_level)

        if tl_closed_above:
            tl_xs.append(i); tl_ys.append(tl_level)
            save_tl(); tl_xs = []; tl_ys = []; tl_active = False
        elif tl_active and not np.isnan(sma_i) and cl_i < sma_i:
            tl_xs.append(i); tl_ys.append(tl_level)
            save_tl(); tl_xs = []; tl_ys = []; tl_active = False
        elif tl_active and not np.isnan(tl_val):
            tl_xs.append(i); tl_ys.append(tl_val)

    save_hz(); save_tl()

    # ── Pending: active line levels at the very last bar (no break yet) ───
    # If a line is still alive at bar N-1, the stock is "waiting for break".
    pending = []
    last_i  = N - 1
    if hz_active and not np.isnan(ph0_v):
        pending.append(dict(kind='hz', level=round(ph0_v, 4)))
    if tl_active and not np.isnan(tl_slope) and tl_base_i >= 0:
        tl_now = tl_base + tl_slope * (last_i - tl_base_i)
        if not np.isnan(tl_now):
            import math as _math
            tl_ang = round(abs(_math.degrees(_math.atan(tl_slope))), 1)
            pending.append(dict(kind='tl', level=round(tl_now, 4), tl_angle=tl_ang))

    return all_breaks, hz_lines, tl_lines, pending
