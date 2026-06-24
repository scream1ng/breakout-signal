"""
chart_interactive.py — chart-data builder.
  get_chart_data(df, ticker, stock, all_breaks, hz_lines, tl_lines,
                 rvol_arr, is_gap_arr, cfg, trades=None) -> dict

Returns the per-stock dict (candles, EMAs, SMAs, signals, trades, level
segments) consumed by the web app (/api/chart/{ticker}) and the --view tool.
"""

import pandas as pd


# ── Colour theme (matching dark TradingView style) ────────────────────────────
BG      = '#131722'
PANEL   = '#1e222d'
GRID    = '#2a2e39'
TEXT    = '#9598a1'
WHITE   = '#d1d4dc'

# Candle colours
UP_HV   = '#2196F3'   # blue  — up + high vol
DN_HV   = '#FFD700'   # yellow — down + high vol
UP_NV   = '#26a69a'   # teal  — up normal
DN_NV   = '#ef5350'   # red   — down normal
GREY_C  = '#444444'   # grey  — low vol


def _candle_color(o, c, rv, rvol_min):
    if rv < 0.5:        return GREY_C, GREY_C
    if c >= o:
        col = UP_HV if rv >= rvol_min else UP_NV
    else:
        col = DN_HV if rv >= rvol_min else DN_NV
    return col, col


def _build_chart_data(
    df, ticker, stock, all_breaks, hz_lines, tl_lines,
    rvol_arr, is_gap_arr, cfg, trades=None
) -> dict:
    """Build the chart data dict (no file I/O). Used by both draw_interactive_chart and get_chart_data."""
    N          = len(df)
    rvol_min   = cfg['rvol_min']
    rsm_min    = cfg['rsm_min']
    capital    = cfg['capital']
    risk_pct   = cfg['risk_pct']
    commission = cfg['commission']
    psth_fast  = cfg['psth_fast']
    psth_slow  = cfg['psth_slow']

    dates  = [str(d.date()) if hasattr(d, 'date') else str(d) for d in df.index]

    candles = []
    for i in range(N):
        o = float(df['Open'].iloc[i]); c = float(df['Close'].iloc[i])
        h = float(df['High'].iloc[i]);  l = float(df['Low'].iloc[i])
        rv = float(rvol_arr[i])
        body_col, _ = _candle_color(o, c, rv, rvol_min)
        candles.append({'i':i,'d':dates[i],'o':round(o,4),'h':round(h,4),
                        'l':round(l,4),'c':round(c,4),'rv':round(rv,2),
                        'col':body_col})

    def ma_series(col):
        return [None if pd.isna(df[col].iloc[i]) else round(float(df[col].iloc[i]),4)
                for i in range(N)]

    ema10  = ma_series('EMA10')
    ema20  = ma_series('EMA20')
    sma50  = ma_series('SMA50')
    sma200 = ma_series('SMA200')
    rsm_s  = [None if pd.isna(df['RSM'].iloc[i]) else round(float(df['RSM'].iloc[i]),1)
              for i in range(N)]
    rvol_s = [round(float(rvol_arr[i]),2) for i in range(N)]
    gap_s  = [bool(is_gap_arr[i]) for i in range(N)]

    _, hz3, hz7 = hz_lines
    _, tl3, tl7 = tl_lines
    hz_fast_json = [{'xs': xs, 'ys': [round(y,4) for y in ys]} for xs,ys in hz3]
    hz_slow_json = [{'xs': xs, 'ys': [round(y,4) for y in ys]} for xs,ys in hz7]
    tl_fast_json = [{'xs': xs, 'ys': [round(y,4) for y in ys]} for xs,ys in tl3]
    tl_slow_json = [{'xs': xs, 'ys': [round(y,4) for y in ys]} for xs,ys in tl7]

    signals_json = []
    for brk in all_breaks:
        i   = brk['bar']
        bp  = brk['bp']
        atr = brk['atr']
        sl  = round(bp - atr * cfg['sl_mult'], 4)   if atr > 0 else None
        tp1 = round(bp + atr * cfg['tp1_mult'], 4)  if atr > 0 else None
        tp2 = round(bp + atr * cfg['tp2_mult'], 4)  if atr > 0 else None
        sl_pct  = round((sl  - bp) / bp * 100, 2) if sl  else None
        tp1_pct = round((tp1 - bp) / bp * 100, 2) if tp1 else None
        tp2_pct = round((tp2 - bp) / bp * 100, 2) if tp2 else None
        rr  = round(abs(tp1_pct / sl_pct), 1) if sl_pct and tp1_pct and sl_pct != 0 else None

        stretch_v = brk.get('stretch', 0)
        if stretch_v > 4:
            col = '#ef5350'; label = 'STR >4';  filter_type = 'STR'
        elif not brk['regime_ok']:
            col = '#555555'; label = 'Below SMA50';             filter_type = 'Below'
        elif brk['rvol_ok'] and brk['rsm_ok']:
            col = '#ff6ec7'; label = 'Prime (RVOL+RSM+SMA50)'; filter_type = 'Prime'
        elif brk['rvol_ok']:
            col = '#2196F3'; label = f"RVOL (RSM {brk['rsm']:.0f} < {rsm_min})"; filter_type = 'RVOL'
        elif brk['rsm_ok']:
            col = '#4caf50'; label = 'RSM (no RVOL)';          filter_type = 'RSM'
        else:
            col = '#ffd740'; label = 'SMA50 only';             filter_type = 'SMA50'

        signals_json.append(dict(
            i=i, bar_y=round(float(df['High'].iloc[i]),4),
            bp=round(bp,4), kind=brk['kind'], date=brk['date'],
            rsm=brk['rsm'], rvol=brk['rvol'], atr=round(atr,4),
            close=brk['close'], sma50=brk['sma50'],
            stretch=brk.get('stretch', 0),
            sl=sl, tp1=tp1, tp2=tp2,
            sl_pct=sl_pct, tp1_pct=tp1_pct, tp2_pct=tp2_pct, rr=rr,
            rsm_ok=brk['rsm_ok'], rvol_ok=brk['rvol_ok'], regime_ok=brk['regime_ok'],
            col=col, label=label, filter_type=filter_type,
        ))

    last_close = round(float(df['Close'].iloc[-1]), 4)
    rsm_now    = rsm_s[-1] or 0
    rvol_now   = rvol_s[-1] if rvol_s else 0

    # Serialize trades for JS
    trades_json = []
    for t in (trades or []):
        trades_json.append(dict(
            entry_bar   = t.get('entry_bar'),
            exit_bar    = t.get('exit_bar'),
            tp1_bar     = t.get('tp1_bar'),
            tp2_bar     = t.get('tp2_bar'),
            tp1_hit     = bool(t.get('tp1_hit')),
            tp2_hit     = bool(t.get('tp2_hit')),
            exit_reason = t.get('exit_reason',''),
            entry_price = round(float(t.get('entry_price',0)),4),
            exit_price  = round(float(t.get('exit_price') or 0),4),
            sl          = round(float(t.get('sl',0)),4),
            tp1         = round(float(t.get('tp1',0)),4),
            tp2         = round(float(t.get('tp2',0)),4),
            ret_pct     = round(float(t.get('entry_return_pct',0)),2),
            entry_date  = str(t.get('entry_date','')),
            exit_date   = str(t.get('exit_date','')),
            filter_type = t.get('filter_type','Prime'),
            win         = bool(t.get('total_pnl',0) > 0),
            stretch     = round(float(t.get('stretch', 0)), 2),
        ))

    return dict(
        ticker=ticker, desc=stock.get('desc',''), sector=stock.get('sector',''),
        rsm_now=rsm_now, rvol_now=rvol_now, rsm_min=rsm_min, rvol_min=rvol_min,
        last_close=last_close, capital=capital, risk_pct=risk_pct,
        commission=commission, psth_fast=psth_fast, psth_slow=psth_slow,
        candles=candles, ema10=ema10, ema20=ema20, sma50=sma50, sma200=sma200,
        rsm=rsm_s, rvol=rvol_s, gaps=gap_s,
        hz_fast=hz_fast_json, hz_slow=hz_slow_json,
        tl_fast=tl_fast_json, tl_slow=tl_slow_json,
        signals=signals_json,
        trades=trades_json,
        sl_mult=cfg['sl_mult'], tp1_mult=cfg['tp1_mult'], tp2_mult=cfg['tp2_mult'],
        be_days=cfg['be_days'],
    )


def get_chart_data(
    df, ticker, stock, all_breaks, hz_lines, tl_lines,
    rvol_arr, is_gap_arr, cfg, trades=None
) -> dict:
    """Return chart data dict for embedding in combined HTML. No file saved."""
    return _build_chart_data(df, ticker, stock, all_breaks, hz_lines, tl_lines,
                             rvol_arr, is_gap_arr, cfg, trades=trades)

