"""
chart.py — Chart drawing
  draw_chart(df, ticker, stock, pb_trades, pb_buy, pb_sell,
             hz_lines, tl_lines, rvol_arr, is_gap_arr, cfg,
             charts_dir, date_str)
      -> fname (str)   e.g. 'DELTA_BK_2026_03_10.png'

Layout: 3 panels
  Top    — candlesticks + EMA10/EMA20/SMA50/SMA200 + pivot lines + trade annotations
  Middle — RSM (yellow line)
  Bottom — RVol bars + threshold line
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['text.usetex']        = False
matplotlib.rcParams['mathtext.default']   = 'regular'
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from matplotlib.patches import Rectangle
import matplotlib.lines as mlines

# ── Theme ────────────────────────────────────────────────────────────────────
BG, PANEL, GRID_, TEXT, WHITE = '#131722', '#1e222d', '#2a2e39', '#9598a1', '#d1d4dc'

# Candle / volume colour map
#   grey  — RVol < 0.5x (very low volume)
#   green — up, normal vol
#   red   — down, normal vol
#   hvup  — up, RVol >= threshold (blue)
#   hvdn  — down, RVol >= threshold (yellow)
CC = {
    'grey': dict(b='#444444', w='#555555', v='#444444'),
    'green':dict(b='#26a69a', w='#26a69a', v='#26a69a'),
    'red':  dict(b='#ef5350', w='#ef5350', v='#ef5350'),
    'hvup': dict(b='#2196F3', w='#2196F3', v='#2196F3'),
    'hvdn': dict(b='#FFD700', w='#FFD700', v='#b8960a'),
}


def _candle_types(df: pd.DataFrame, rvol_arr: np.ndarray, rvol_min: float) -> list[str]:
    ct = []
    for i in range(len(df)):
        o  = float(df['Open'].iloc[i])
        c  = float(df['Close'].iloc[i])
        rv = float(rvol_arr[i])
        if rv < 0.5:
            ct.append('grey')
        elif c >= o:
            ct.append('hvup' if rv >= rvol_min else 'green')
        else:
            ct.append('hvdn' if rv >= rvol_min else 'red')
    return ct


def draw_chart(
    df:          pd.DataFrame,
    ticker:      str,
    stock:       dict,
    pb_trades:   list,
    pb_buy:      list,
    pb_sell:     list,
    hz_lines:    tuple,         # ('dual', hz3_list, hz7_list)
    tl_lines:    tuple,         # ('dual', tl3_list, tl7_list)
    rvol_arr:    np.ndarray,
    is_gap_arr:  np.ndarray,
    cfg:         dict,
    charts_dir:  str,
    date_str:    str,
) -> str:
    """Draw and save chart PNG. Returns filename."""
    N        = len(df)
    xi       = np.arange(N)
    rvol_min = cfg['rvol_min']
    rsm_min  = cfg['rsm_min']
    capital  = cfg['capital']
    risk_pct = cfg['risk_pct']
    psth_fast= cfg['psth_fast']
    psth_slow= cfg['psth_slow']
    commission = cfg['commission']

    total_pnl     = sum(t['total_pnl'] for t in pb_trades)
    total_pnl_pct = total_pnl / capital * 100
    win_rate      = (len([t for t in pb_trades if t['total_pnl'] > 0]) / len(pb_trades) * 100
                     if pb_trades else 0)
    rsm_now_raw   = df['RSM'].iloc[-1]
    rsm_now       = float(rsm_now_raw) if not pd.isna(rsm_now_raw) else 0.0

    candle_types  = _candle_types(df, rvol_arr, rvol_min)

    # ── Figure / axes ─────────────────────────────────────────────────────
    fig = plt.figure(figsize=(28, 15), facecolor=BG)
    gs  = gridspec.GridSpec(3, 1, height_ratios=[5.5, 0.9, 0.9], hspace=0.04,
                            left=0.012, right=0.965, top=0.930, bottom=0.055)
    ax   = fig.add_subplot(gs[0])
    arsm = fig.add_subplot(gs[1], sharex=ax)
    arvl = fig.add_subplot(gs[2], sharex=ax)

    for a in [ax, arsm, arvl]:
        a.set_facecolor(BG)
        a.tick_params(colors=TEXT, labelsize=7.5, length=3)
        for sp in a.spines.values(): sp.set_edgecolor(GRID_)

    # ── Candlesticks ──────────────────────────────────────────────────────
    W = 0.55
    for i in range(N):
        ct = candle_types[i]; cm = CC[ct]
        o, h, l, c = (float(df[col].iloc[i]) for col in ['Open', 'High', 'Low', 'Close'])
        ax.plot([i, i], [l, h], color=cm['w'], lw=0.7, zorder=2)
        blo = min(o, c); bh = max(abs(c - o), c * 0.001)
        ax.add_patch(Rectangle((i - W / 2, blo), W, bh, zorder=3,
                                facecolor=cm['b'], edgecolor='none', lw=0))

    # ── MA lines ──────────────────────────────────────────────────────────
    ax.plot(xi, df['EMA10'],  color='#26a69a', lw=1.3,        zorder=4)
    ax.plot(xi, df['EMA20'],  color='#f9a825', lw=1.0, ls='--', zorder=4)
    ax.plot(xi, df['SMA50'],  color='#ef5350', lw=1.8,        zorder=4)
    ax.plot(xi, df['SMA200'], color='#ef5350', lw=0.9, alpha=0.25, zorder=4)

    # ── Pivot lines ───────────────────────────────────────────────────────
    _, hz3, hz7 = hz_lines
    for (xs, ys) in hz3:
        ax.plot(xs, ys, color='#ff9800', lw=1.0, ls='--', alpha=0.70, zorder=5)
    for (xs, ys) in hz7:
        ax.plot(xs, ys, color='#ffcc02', lw=1.2, ls='--', alpha=0.85, zorder=5)

    _, tl3, tl7 = tl_lines
    for (xs, ys) in tl3:
        ax.plot(xs, ys, color='#ff9800', lw=1.4, ls='-', alpha=0.70, zorder=6)
    for (xs, ys) in tl7:
        ax.plot(xs, ys, color='#ffcc02', lw=2.0, ls='-', alpha=0.90, zorder=6)

    # ── Entry arrows — pink ▲ from candle low (matches P&L, original style) ─
    def up_arrow(x, price, color, label, offset=0.030):
        yt = price * (1 - offset)
        ax.annotate('', xy=(x, price * 0.9995), xytext=(x, yt),
                    arrowprops=dict(arrowstyle='->', color=color, lw=1.8, mutation_scale=13),
                    zorder=9)
        ax.text(x, yt * 0.991, label, color=color, fontsize=5.5,
                ha='center', va='top', fontweight='bold', zorder=10)

    for t in pb_trades:
        eb = t['entry_bar']
        up_arrow(eb, float(df['Low'].iloc[eb]), '#ff6ec7', 'Entry')

    # ── SL / TP lines for simulated trades ───────────────────────────────
    for t in pb_trades:
        eb = t['entry_bar']
        ex = t['exit_bar'] if t['exit_bar'] is not None else N - 1
        ax.plot([eb, min(ex, N-1)], [t['sl'],  t['sl']],
                color='#ff1744', lw=0.7, ls='--', alpha=0.35, zorder=5)
        if not t['tp1_hit']:
            ax.plot([eb, min(ex, N-1)], [t['tp1'], t['tp1']],
                    color='#69f0ae', lw=0.6, ls=':', alpha=0.35, zorder=5)
        if not t['tp2_hit']:
            ax.plot([eb, min(ex, N-1)], [t['tp2'], t['tp2']],
                    color='#00e676', lw=0.6, ls=':', alpha=0.35, zorder=5)

    # ── Exit arrows for simulated trades ──────────────────────────────────
    def down_arrow(x, price, color, label, offset=0.022):
        yt = price * (1 + offset)
        ax.annotate('', xy=(x, price * 1.0005), xytext=(x, yt),
                    arrowprops=dict(arrowstyle='->', color=color, lw=1.8, mutation_scale=13),
                    zorder=9)
        ax.text(x, yt * 1.008, label, color=color, fontsize=5.5,
                ha='center', va='bottom', fontweight='bold', zorder=10)

    for t in pb_trades:
        ex  = t['exit_bar'] if t['exit_bar'] is not None else N - 1
        if t['tp1_hit'] and t['tp1_bar'] is not None:
            down_arrow(t['tp1_bar'], t['tp1'], '#69f0ae', 'TP1')
        if t['tp2_hit'] and t['tp2_bar'] is not None:
            down_arrow(t['tp2_bar'], t['tp2'], '#00e676', 'TP2')
        rsn = t['exit_reason']
        if rsn == 'SL':
            lbl, col = 'SL',   '#ff1744'
        elif rsn == 'EMA10':
            lbl, col = 'Exit', '#ff9800'
        else:
            lbl, col = 'Exit', '#aaaaaa'
        down_arrow(ex, float(df['High'].iloc[ex]), col, lbl, offset=0.026)

    # ── RSM panel ─────────────────────────────────────────────────────────
    rsm_vals = df['RSM'].values
    arsm.plot(xi, rsm_vals, color='#ffd740', lw=1.1, alpha=0.90, zorder=4)
    arsm.axhline(rsm_min, color='#ffd740', lw=0.8, ls=':', alpha=0.8)
    arsm.fill_between(xi, 0, 100,
                      where=~np.isnan(rsm_vals) & (rsm_vals >= rsm_min),
                      color='#ffd740', alpha=0.08, zorder=1)
    arsm.set_ylim(0, 100)
    arsm.yaxis.set_label_position('right'); arsm.yaxis.tick_right()
    arsm.set_ylabel('RSM', color='#ffd740', fontsize=6, rotation=0, labelpad=22, va='center')
    arsm.tick_params(axis='y', labelsize=6, colors='#ffd740')

    # ── RVol panel ────────────────────────────────────────────────────────
    for i in range(N):
        rv  = float(rvol_arr[i])
        col = '#26a69a' if rv >= rvol_min else '#555555'
        arvl.bar(i, rv, color=col, alpha=0.85, width=0.7, zorder=2)
        if bool(is_gap_arr[i]):
            arvl.plot(i, rv + 0.05, marker='o', color='#ffd740', ms=3, zorder=4)
    arvl.axhline(rvol_min, color='#ff9800', lw=0.9, ls='--', alpha=0.8, zorder=3)
    arvl.axhline(1.0,      color=TEXT,      lw=0.5, ls=':',  alpha=0.4, zorder=3)
    arvl.set_ylim(0, max(rvol_arr.max() * 1.1, rvol_min * 2))
    arvl.yaxis.set_label_position('right'); arvl.yaxis.tick_right()
    arvl.set_ylabel(f'RVol\n{rvol_min}x', color='#ff9800', fontsize=6,
                    rotation=0, labelpad=28, va='center')
    arvl.tick_params(axis='y', labelsize=5.5, colors=TEXT)

    # ── X axis ────────────────────────────────────────────────────────────
    ticks, labels, pm = [], [], None
    for i, d in enumerate(df.index):
        if d.month != pm:
            ticks.append(i)
            labels.append(d.strftime('%b\n%Y') if (d.month == 1 or i == 0) else d.strftime('%b'))
            pm = d.month
    arvl.set_xticks(ticks); arvl.set_xticklabels(labels, color=TEXT, fontsize=8)
    arvl.tick_params(axis='x', length=4)
    plt.setp(ax.get_xticklabels(),   visible=False)
    plt.setp(arsm.get_xticklabels(), visible=False)
    ax.set_xlim(-2, N + 1)
    ax.yaxis.set_label_position('right'); ax.yaxis.tick_right()
    ax.tick_params(axis='y', labelsize=7.5, colors=TEXT)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    lc = float(df['Close'].iloc[-1])
    ax.annotate(f'  {lc:.2f}  ', xy=(N - 1, lc), xytext=(N + 0.5, lc),
                fontsize=8, color='white', va='center', ha='left', zorder=10,
                bbox=dict(facecolor='#ef5350', edgecolor='none', boxstyle='round,pad=0.3'))

    for a in [ax, arsm, arvl]:
        a.yaxis.grid(True, color=GRID_, lw=0.4, alpha=0.5)
        a.xaxis.grid(True, color=GRID_, lw=0.3, alpha=0.25)
        a.set_axisbelow(True)

    # ── Legend ────────────────────────────────────────────────────────────
    leg = [
        mlines.Line2D([],[],color='#26a69a',lw=1.3,          label='EMA10'),
        mlines.Line2D([],[],color='#f9a825',lw=1.0,ls='--',  label='EMA20'),
        mlines.Line2D([],[],color='#ef5350',lw=1.8,           label='SMA50'),
        mlines.Line2D([],[],color='#ffcc02',lw=1.2,ls='--',  label=f'Hz Pivot (psth={psth_slow})'),
        mlines.Line2D([],[],color='#ff9800',lw=1.0,ls='--',  label=f'Hz Pivot (psth={psth_fast})'),
        mlines.Line2D([],[],color='#ffcc02',lw=2.0,           label=f'LH TL (psth={psth_slow})'),
        mlines.Line2D([],[],color='#ff9800',lw=1.4,           label=f'LH TL (psth={psth_fast})'),
        mlines.Line2D([],[],color='#ff1744',lw=0.8,ls='--',  label='SL'),
        mlines.Line2D([],[],color='#69f0ae',lw=0.7,ls=':',   label='TP1 2xATR'),
        mlines.Line2D([],[],color='#00e676',lw=0.7,ls=':',   label='TP2 4xATR'),
        mlines.Line2D([],[],color='#00e676',lw=0,marker='v',ms=7, label='Entry (all pass)'),
        mlines.Line2D([],[],color='#ffd740',lw=0,marker='v',ms=7, label='Entry (RSM fail)'),
        mlines.Line2D([],[],color='#2196F3',lw=0,marker='v',ms=7, label='Entry (RVol fail)'),
        mlines.Line2D([],[],color='#888888',lw=0,marker='v',ms=7, label='Entry (below SMA50)'),
        mlines.Line2D([],[],color='#69f0ae',lw=0,marker='v',ms=7, label='TP1'),
        mlines.Line2D([],[],color='#00e676',lw=0,marker='v',ms=7, label='TP2'),
        mlines.Line2D([],[],color='#ff1744',lw=0,marker='v',ms=7, label='SL exit'),
        mlines.Line2D([],[],color='#ff9800',lw=0,marker='v',ms=7, label='EMA10 exit'),
        mlines.Line2D([],[],color='#2196F3',lw=0,marker='s',ms=7, label='Up HiVol'),
        mlines.Line2D([],[],color='#FFD700',lw=0,marker='s',ms=7, label='Dn HiVol'),
        mlines.Line2D([],[],color='#26a69a',lw=0,marker='s',ms=7, label='Up Normal'),
        mlines.Line2D([],[],color='#ef5350',lw=0,marker='s',ms=7, label='Dn Normal'),
    ]
    ax.legend(handles=leg, loc='upper left', facecolor=PANEL, edgecolor=GRID_,
              labelcolor=TEXT, fontsize=7, framealpha=0.93, ncol=6,
              handlelength=1.4, columnspacing=0.9)

    # ── Title / stats ─────────────────────────────────────────────────────
    pnl_color = '#00e676' if total_pnl >= 0 else '#ef5350'
    fig.text(0.014, 0.958, f'{ticker}  {stock["desc"]}  {stock["sector"]}  1D',
             color=WHITE, fontsize=11, fontweight='bold', va='top')
    fig.text(0.014, 0.936,
             f'RSM today: {rsm_now:.0f}   Filter: RSM>{rsm_min} rolling (no look-ahead)'
             f'   RVol>{rvol_min}x required (gap≥0.3% shown as dot)'
             f'   Entry: candle high touches level   Commission: {commission*100:.2f}pct/side',
             color='#ffd740', fontsize=7.5, va='top')
    fig.text(0.014, 0.923,
             f'Capital {capital:,.0f}   Risk {risk_pct*100:.1f}pct/trade   '
             f'PB: {len(pb_trades)}T  WR {win_rate:.0f}pct  PnL {total_pnl:+,.0f}',
             color=TEXT, fontsize=7, va='top')
    fig.text(0.965, 0.958, f'Total PnL  {total_pnl:+,.0f}  ({total_pnl_pct:+.1f}pct)',
             color=pnl_color, fontsize=10, fontweight='bold', va='top', ha='right')

    # ── Save ──────────────────────────────────────────────────────────────
    safe  = ticker.replace('.', '_').replace('=', '_')
    fname = f'{safe}_{date_str}.png'
    plt.savefig(os.path.join(charts_dir, fname), dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close()
    print(f'  Chart saved: {fname}')
    return fname