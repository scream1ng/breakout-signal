"""
chart_interactive.py — Interactive Plotly HTML chart
  draw_interactive_chart(df, ticker, stock, all_breaks, hz_lines, tl_lines,
                         rvol_arr, is_gap_arr, cfg, charts_dir, date_str)
      -> html_fname

All possible breaks are shown as coloured markers:
  🟢 Green  — all gates pass (regime + RVol + RSM)
  🟡 Yellow — regime + RVol pass, RSM fails
  🔵 Blue   — regime passes, RVol fails
  ⚪ Grey   — regime fails (price below SMA50)

Click any marker → analysis panel shows entry / SL / TP levels + filter status.
"""

import os
import json
import numpy as np
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
    rvol_arr, is_gap_arr, cfg
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

        all_pass = brk['regime_ok'] and brk['rvol_ok'] and brk['rsm_ok']
        if all_pass:
            col = '#ff6ec7'; label = 'ENTRY (all pass)'
        elif not brk['regime_ok']:
            col = '#888888'; label = 'Below SMA50'
        elif not brk['rsm_ok'] and brk['rvol_ok']:
            col = '#2196F3'; label = f'High RVol, RSM {brk["rsm"]:.0f} < {rsm_min}'
        elif not brk['rsm_ok']:
            col = '#ffd740'; label = f'RSM {brk["rsm"]:.0f} < {rsm_min}'
        else:
            col = '#26a69a'; label = f'RVol {brk["rvol"]:.1f}x (normal)'

        signals_json.append(dict(
            i=i, bar_y=round(float(df['High'].iloc[i]),4),
            bp=round(bp,4), kind=brk['kind'], date=brk['date'],
            rsm=brk['rsm'], rvol=brk['rvol'], atr=round(atr,4),
            close=brk['close'], sma50=brk['sma50'],
            sl=sl, tp1=tp1, tp2=tp2,
            sl_pct=sl_pct, tp1_pct=tp1_pct, tp2_pct=tp2_pct, rr=rr,
            rsm_ok=brk['rsm_ok'], rvol_ok=brk['rvol_ok'], regime_ok=brk['regime_ok'],
            col=col, label=label,
        ))

    last_close = round(float(df['Close'].iloc[-1]), 4)
    rsm_now    = rsm_s[-1] or 0
    rvol_now   = rvol_s[-1] if rvol_s else 0

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
        sl_mult=cfg['sl_mult'], tp1_mult=cfg['tp1_mult'], tp2_mult=cfg['tp2_mult'],
        be_days=cfg['be_days'],
    )


def get_chart_data(
    df, ticker, stock, all_breaks, hz_lines, tl_lines,
    rvol_arr, is_gap_arr, cfg
) -> dict:
    """Return chart data dict for embedding in combined HTML. No file saved."""
    return _build_chart_data(df, ticker, stock, all_breaks, hz_lines, tl_lines,
                             rvol_arr, is_gap_arr, cfg)


def draw_interactive_chart(
    df:          pd.DataFrame,
    ticker:      str,
    stock:       dict,
    all_breaks:  list,
    hz_lines:    tuple,
    tl_lines:    tuple,
    rvol_arr:    np.ndarray,
    is_gap_arr:  np.ndarray,
    cfg:         dict,
    charts_dir:  str,
    date_str:    str,
) -> str:
    """Build self-contained interactive HTML. Returns filename."""
    data      = _build_chart_data(df, ticker, stock, all_breaks, hz_lines, tl_lines,
                                  rvol_arr, is_gap_arr, cfg)
    data_json = json.dumps(data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{ticker} — Interactive Chart</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@600;700;800&display=swap');
  :root {{
    --bg:#131722; --panel:#1e222d; --border:#2a2e39; --text:#9598a1;
    --white:#d1d4dc; --accent:#00e5cc; --green:#00e676; --red:#ef5350;
    --yellow:#ffd740; --blue:#2196F3; --orange:#ff9800;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  html,body {{ height:100%; background:var(--bg); color:var(--white);
               font-family:'DM Mono',monospace; overflow:hidden; }}
  .app {{ display:grid; grid-template-columns:1fr 320px; grid-template-rows:48px 1fr;
          height:100vh; }}
  header {{ grid-column:1/-1; display:flex; align-items:center; gap:14px;
            padding:0 18px; background:var(--panel);
            border-bottom:1px solid var(--border); flex-shrink:0; }}
  .logo {{ font-family:'Syne',sans-serif; font-weight:800; font-size:15px;
           letter-spacing:.08em; color:var(--accent); }}
  .hticker {{ font-family:'Syne',sans-serif; font-weight:700; font-size:16px; color:var(--white); }}
  .hinfo {{ font-size:11px; color:var(--text); }}
  .hrsm {{ margin-left:auto; font-size:12px; color:var(--yellow);
           font-weight:500; letter-spacing:.04em; }}
  .chart-area {{ position:relative; overflow:hidden; background:var(--bg); }}
  canvas {{ position:absolute; top:0; left:0; }}
  .panel {{ background:var(--panel); border-left:1px solid var(--border);
            overflow-y:auto; display:flex; flex-direction:column; }}
  .panel::-webkit-scrollbar {{ width:4px; }}
  .panel::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:2px; }}

  /* Signal list */
  .sig-header {{ padding:12px 14px 8px; border-bottom:1px solid var(--border);
                 font-size:11px; color:var(--text); letter-spacing:.06em; flex-shrink:0; }}
  .sig-list {{ flex:1; overflow-y:auto; }}
  .sig-item {{ padding:9px 14px; cursor:pointer; border-bottom:1px solid var(--border);
               transition:background .12s; display:flex; align-items:center; gap:10px; }}
  .sig-item:hover {{ background:rgba(0,229,204,.06); }}
  .sig-item.active {{ background:rgba(0,229,204,.13); border-left:2px solid var(--accent); }}
  .sig-dot {{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }}
  .sig-info {{ flex:1; }}
  .sig-date {{ font-size:11px; color:var(--white); font-weight:500; }}
  .sig-sub  {{ font-size:10px; color:var(--text); margin-top:1px; }}

  /* Analysis card */
  .analysis {{ border-top:1px solid var(--border); padding:14px; flex-shrink:0; }}
  .an-title {{ font-family:'Syne',sans-serif; font-weight:700; font-size:13px;
               color:var(--accent); margin-bottom:10px; letter-spacing:.04em; }}
  .an-row {{ display:flex; justify-content:space-between; align-items:center;
             padding:4px 0; border-bottom:1px solid var(--border); font-size:11px; }}
  .an-row:last-child {{ border-bottom:none; }}
  .an-label {{ color:var(--text); }}
  .an-value {{ color:var(--white); font-weight:500; text-align:right; }}
  .an-value.green {{ color:var(--green); }}
  .an-value.red   {{ color:var(--red);   }}
  .an-value.yellow{{ color:var(--yellow);}}
  .an-value.blue  {{ color:var(--blue);  }}
  .an-value.grey  {{ color:#888; }}
  .an-sep {{ height:1px; background:var(--border); margin:8px 0; }}
  .an-empty {{ color:var(--text); font-size:11px; text-align:center;
               padding:20px 0; opacity:.6; }}
  .filter-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }}
  .badge {{ font-size:9.5px; padding:2px 8px; border-radius:10px;
            font-weight:600; letter-spacing:.04em; }}
  .badge.pass {{ background:rgba(0,230,118,.15); color:var(--green); border:1px solid rgba(0,230,118,.3); }}
  .badge.fail {{ background:rgba(239,83,80,.15);  color:var(--red);   border:1px solid rgba(239,83,80,.3); }}

  /* Legend */
  .legend {{ display:flex; gap:12px; flex-wrap:wrap; padding:6px 18px;
             background:var(--panel); border-top:1px solid var(--border);
             font-size:10px; color:var(--text); }}
  .leg-item {{ display:flex; align-items:center; gap:5px; }}
  .leg-dot {{ width:8px; height:8px; border-radius:50%; }}
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">⬡ PB SCANNER</div>
    <div class="hticker" id="h-ticker">—</div>
    <div class="hinfo" id="h-info"></div>
    <div class="hrsm" id="h-rsm"></div>
  </header>

  <div class="chart-area" id="chart-area">
    <canvas id="cv-bg"></canvas>
    <canvas id="cv-main"></canvas>
    <canvas id="cv-overlay"></canvas>
  </div>

  <div class="panel">
    <div class="sig-header">
      BREAKOUT SIGNALS — <span id="sig-count" style="color:var(--white)">0</span>
      <span id="sig-filter-info" style="font-size:10px;display:block;margin-top:2px;opacity:.7"></span>
    </div>
    <div class="sig-list" id="sig-list"></div>
    <div class="analysis" id="analysis">
      <div class="an-empty">← Click a signal to analyse</div>
    </div>
  </div>
</div>

<script>
const D = {data_json};

// ── Chart geometry ─────────────────────────────────────────────────────────
const MARGIN = {{l:8, r:72, t:8, b:28}};
const candles = D.candles;
const N = candles.length;

let W, H, BAR_W, X0, PRICE_MIN, PRICE_MAX, PRICE_RANGE;
let panelHeights; // [main, rsm, rvol]

function resize() {{
  const el = document.getElementById('chart-area');
  W = el.clientWidth; H = el.clientHeight;
  ['cv-bg','cv-main','cv-overlay'].forEach(id => {{
    const c = document.getElementById(id);
    c.width = W; c.height = H;
  }});
  computeScales();
  drawAll();
}}

function computeScales() {{
  const pHMain = 0.62, pHRsm = 0.17, pHVol = 0.17;
  const totalH = H - MARGIN.t - MARGIN.b;
  panelHeights = [totalH * pHMain, totalH * pHRsm, totalH * pHVol];

  BAR_W = Math.max(1.5, (W - MARGIN.l - MARGIN.r) / (N + 4));
  X0    = MARGIN.l + BAR_W * 2;

  // Price range from candles
  let lo = Infinity, hi = -Infinity;
  candles.forEach(c => {{ if(c.h > hi) hi = c.h; if(c.l < lo) lo = c.l; }});
  // include MA lines
  [D.ema10, D.sma50, D.sma200].forEach(arr => arr.forEach(v => {{
    if(v != null) {{ if(v>hi) hi=v; if(v<lo) lo=v; }}
  }}));
  const pad = (hi - lo) * 0.08;
  PRICE_MIN = lo - pad; PRICE_MAX = hi + pad;
  PRICE_RANGE = PRICE_MAX - PRICE_MIN;
}}

function xOf(i)  {{ return X0 + i * BAR_W; }}
function yOf(p, panel=0) {{
  const panelTop = MARGIN.t + panelHeights.slice(0, panel).reduce((a,b)=>a+b,0);
  const panelH   = panelHeights[panel];
  let mn, mx;
  if(panel === 0) {{ mn = PRICE_MIN; mx = PRICE_MAX; }}
  else if(panel === 1) {{ mn = 0; mx = 100; }}
  else {{ mn = 0; mx = Math.max(...D.rvol.filter(v=>v!=null)) * 1.1; if(mx<D.rvol_min*2)mx=D.rvol_min*2; }}
  return panelTop + panelH - (p - mn) / (mx - mn) * panelH;
}}

function panelTop(p) {{
  return MARGIN.t + panelHeights.slice(0,p).reduce((a,b)=>a+b,0);
}}

// ── Drawing ───────────────────────────────────────────────────────────────
function drawAll() {{
  drawBackground();
  drawChart();
}}

function drawBackground() {{
  const cv = document.getElementById('cv-bg');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);

  // Panel backgrounds
  [0,1,2].forEach(p => {{
    ctx.fillStyle = p % 2 === 0 ? '#131722' : '#111520';
    const pt = panelTop(p);
    ctx.fillRect(MARGIN.l, pt, W-MARGIN.l-MARGIN.r, panelHeights[p]);
  }});

  // Horizontal grid lines
  ctx.strokeStyle = '#2a2e39'; ctx.lineWidth = 0.4;
  // Panel 0: price grid
  const steps = 6;
  for(let k=0; k<=steps; k++) {{
    const p = PRICE_MIN + (PRICE_MAX - PRICE_MIN) * k / steps;
    const y = yOf(p, 0);
    ctx.beginPath(); ctx.moveTo(MARGIN.l, y); ctx.lineTo(W-MARGIN.r, y); ctx.stroke();
    ctx.fillStyle = '#9598a1'; ctx.font = '10px DM Mono';
    ctx.fillText(p.toFixed(2), W-MARGIN.r+3, y+3);
  }}

  // Panel 1: RSM grid at 25,50,75
  [25,50,75].forEach(v => {{
    const y = yOf(v,1);
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
  }});

  // X-axis month labels
  let pm = -1;
  candles.forEach((c,i) => {{
    const d = new Date(c.d);
    if(d.getMonth() !== pm) {{
      pm = d.getMonth();
      const x = xOf(i);
      ctx.fillStyle = '#9598a1'; ctx.font = '9px DM Mono'; ctx.textAlign='center';
      const lbl = d.toLocaleDateString('en',{{month:'short'}}) +
                  (d.getMonth()===0 ? '\\n'+d.getFullYear() : '');
      ctx.fillText(lbl, x, H - MARGIN.b + 12);
    }}
  }});

  // Panel separators
  [1,2].forEach(p => {{
    const y = panelTop(p);
    ctx.strokeStyle = '#2a2e39'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
  }});

  // Panel labels
  ctx.fillStyle='#ffd740'; ctx.font='9px DM Mono'; ctx.textAlign='right';
  ctx.fillText('RSM', W-MARGIN.r+68, panelTop(1)+12);
  ctx.fillText(`${{D.rvol_min}}x`, W-MARGIN.r+68, panelTop(2)+12);
}}

function drawChart() {{
  const cv  = document.getElementById('cv-main');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);

  // ── Pivot lines ────────────────────────────────────────────────────────
  const drawLines = (arr, col, lw, dash=[]) => {{
    arr.forEach(seg => {{
      ctx.strokeStyle=col; ctx.lineWidth=lw; ctx.setLineDash(dash);
      ctx.beginPath();
      for(let k=0; k<seg.xs.length; k++) {{
        const x=xOf(seg.xs[k]); const y=yOf(seg.ys[k],0);
        k===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
      }}
      ctx.stroke();
    }});
    ctx.setLineDash([]);
  }};
  drawLines(D.hz_fast,'#ff9800',1.0,[4,3]);
  drawLines(D.hz_slow,'#ffcc02',1.2,[4,3]);
  drawLines(D.tl_fast,'#ff9800',1.4);
  drawLines(D.tl_slow,'#ffcc02',2.0);

  // ── Candlesticks ──────────────────────────────────────────────────────
  const bw = Math.max(1, BAR_W * 0.55);
  candles.forEach((c,i) => {{
    const x = xOf(i);
    // Wick
    ctx.strokeStyle = c.col; ctx.lineWidth=0.8;
    ctx.beginPath(); ctx.moveTo(x,yOf(c.h,0)); ctx.lineTo(x,yOf(c.l,0)); ctx.stroke();
    // Body
    const yO=yOf(c.o,0); const yC=yOf(c.c,0);
    const bTop=Math.min(yO,yC); const bH=Math.max(Math.abs(yO-yC),1.5);
    ctx.fillStyle=c.col;
    ctx.fillRect(x-bw/2, bTop, bw, bH);
  }});

  // ── MA lines ──────────────────────────────────────────────────────────
  const drawMA = (arr, col, lw, dash=[]) => {{
    ctx.strokeStyle=col; ctx.lineWidth=lw; ctx.setLineDash(dash);
    let started=false;
    ctx.beginPath();
    arr.forEach((v,i) => {{
      if(v==null){{started=false;return;}}
      const x=xOf(i); const y=yOf(v,0);
      if(!started){{ctx.moveTo(x,y);started=true;}}else{{ctx.lineTo(x,y);}}
    }});
    ctx.stroke(); ctx.setLineDash([]);
  }};
  drawMA(D.sma200,'#ef5350',0.9,[3,3]);
  drawMA(D.sma50, '#ef5350',1.8);
  drawMA(D.ema20, '#f9a825',1.0,[4,2]);
  drawMA(D.ema10, '#26a69a',1.3);

  // ── Signal markers ────────────────────────────────────────────────────
  D.signals.forEach((s,idx) => {{
    const x    = xOf(s.i);
    const topY = yOf(s.bar_y, 0);
    const y    = topY - 10;
    ctx.fillStyle = s.col;
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2); ctx.fill();
    ctx.strokeStyle='#131722'; ctx.lineWidth=1; ctx.stroke();
  }});

  // Last close label
  const lc = D.last_close;
  const ly = yOf(lc,0);
  ctx.fillStyle='#ef5350';
  ctx.fillRect(W-MARGIN.r+1, ly-8, MARGIN.r-2, 16);
  ctx.fillStyle='white'; ctx.font='bold 10px DM Mono'; ctx.textAlign='center';
  ctx.fillText(lc.toFixed(2), W-MARGIN.r+MARGIN.r/2, ly+4);

  // ── RSM panel ─────────────────────────────────────────────────────────
  ctx.strokeStyle='#ffd740'; ctx.lineWidth=1.1; ctx.setLineDash([]);
  let started=false; ctx.beginPath();
  D.rsm.forEach((v,i) => {{
    if(v==null){{started=false;return;}}
    const x=xOf(i); const y=yOf(v,1);
    if(!started){{ctx.moveTo(x,y);started=true;}}else{{ctx.lineTo(x,y);}}
  }});
  ctx.stroke();
  // RSM threshold line
  ctx.strokeStyle='rgba(255,215,64,.5)'; ctx.lineWidth=0.8; ctx.setLineDash([4,3]);
  const yRsmMin=yOf(D.rsm_min,1);
  ctx.beginPath(); ctx.moveTo(MARGIN.l,yRsmMin); ctx.lineTo(W-MARGIN.r,yRsmMin); ctx.stroke();
  ctx.setLineDash([]);

  // ── RVol panel ────────────────────────────────────────────────────────
  D.rvol.forEach((v,i) => {{
    const c = candles[i];
    const col = v >= D.rvol_min ? '#26a69a' : '#3a3a3a';
    const x=xOf(i); const y=yOf(v,2); const base=yOf(0,2);
    ctx.fillStyle=col;
    ctx.fillRect(x-BAR_W*0.4, y, BAR_W*0.8, base-y);
    if(D.gaps[i]) {{
      ctx.fillStyle='#ffd740';
      ctx.beginPath(); ctx.arc(x, y-4, 2.5, 0, Math.PI*2); ctx.fill();
    }}
  }});
  // RVol threshold line
  ctx.strokeStyle='rgba(255,152,0,.7)'; ctx.lineWidth=0.9; ctx.setLineDash([4,3]);
  const yVolMin=yOf(D.rvol_min,2);
  ctx.beginPath(); ctx.moveTo(MARGIN.l,yVolMin); ctx.lineTo(W-MARGIN.r,yVolMin); ctx.stroke();
  ctx.setLineDash([]);
}}

// ── Overlay: highlight selected signal ───────────────────────────────────
function drawOverlay(sigIdx) {{
  const cv  = document.getElementById('cv-overlay');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);
  if(sigIdx == null) return;

  const s = D.signals[sigIdx];
  const x = xOf(s.i);

  // Vertical line
  ctx.strokeStyle='rgba(0,229,204,.25)'; ctx.lineWidth=1; ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(x, MARGIN.t); ctx.lineTo(x, H-MARGIN.b); ctx.stroke();
  ctx.setLineDash([]);

  // Entry price horizontal
  if(s.bp) {{
    const y = yOf(s.bp,0);
    ctx.strokeStyle='rgba(0,230,118,.4)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}

  // SL line
  if(s.sl) {{
    const y = yOf(s.sl,0);
    ctx.strokeStyle='rgba(239,83,80,.5)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle='rgba(239,83,80,.2)';
    ctx.fillRect(x, y, W-MARGIN.r-x, yOf(s.bp,0)-y);
  }}

  // TP1 line
  if(s.tp1) {{
    const y = yOf(s.tp1,0);
    ctx.strokeStyle='rgba(0,230,118,.5)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}
  // TP2 line
  if(s.tp2) {{
    const y = yOf(s.tp2,0);
    ctx.strokeStyle='rgba(0,200,100,.4)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}

  // Big dot on the signal
  ctx.fillStyle=s.col;
  ctx.beginPath(); ctx.arc(x, yOf(s.bar_y,0)-10, 7, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle='white'; ctx.lineWidth=1.5; ctx.stroke();
}}

// ── Signal list ────────────────────────────────────────────────────────────
let selectedIdx = null;

function buildSignalList() {{
  document.getElementById('h-ticker').textContent = D.ticker;
  document.getElementById('h-info').textContent   = `${{D.desc}}  ${{D.sector}}`;
  document.getElementById('h-rsm').textContent    = `RSM ${{D.rsm_now?.toFixed(0)}}  1D`;
  document.getElementById('sig-count').textContent = D.signals.length;
  document.getElementById('sig-filter-info').textContent =
    `RVol>${{D.rvol_min}}x  RSM>${{D.rsm_min}}  (colour = filter status)`;

  const list = document.getElementById('sig-list');
  list.innerHTML = '';

  D.signals.forEach((s, idx) => {{
    const el = document.createElement('div');
    el.className = 'sig-item';
    el.id = 'sig-' + idx;
    const kindLabel = s.kind === 'hz' ? 'Horiz Break' : 'TL Break';
    el.innerHTML = `
      <div class="sig-dot" style="background:${{s.col}}"></div>
      <div class="sig-info">
        <div class="sig-date">${{s.date}}  <span style="color:#888;font-size:9px">${{kindLabel}}</span></div>
        <div class="sig-sub">Entry ฿${{s.bp.toFixed(4)}}  · SL ฿${{s.sl ? s.sl.toFixed(4) : '—'}}  · ${{s.label}}</div>
      </div>
    `;
    el.onclick = () => selectSignal(idx);
    list.appendChild(el);
  }});
}}

function selectSignal(idx) {{
  if(selectedIdx != null)
    document.getElementById('sig-'+selectedIdx)?.classList.remove('active');
  selectedIdx = idx;
  document.getElementById('sig-'+idx)?.classList.add('active');
  document.getElementById('sig-'+idx)?.scrollIntoView({{block:'nearest'}});
  drawOverlay(idx);
  renderAnalysis(idx);
}}

function renderAnalysis(idx) {{
  const s = D.signals[idx];
  const box = document.getElementById('analysis');

  const fmt = (v, d=4) => v != null ? `฿${{v.toFixed(d)}}` : '—';
  const fmtPct = (v) => v != null ? (v>=0?'+':'')+v.toFixed(2)+'%' : '—';
  const pctClass = (v) => v == null ? '' : (v>=0 ? 'green' : 'red');

  const kindFull = s.kind === 'hz' ? 'Horizontal Breakout' : 'Trendline Breakout';

  box.innerHTML = `
    <div class="an-title">SIGNAL ANALYSIS</div>
    <div class="an-row"><span class="an-label">Date</span>
      <span class="an-value">${{s.date}}</span></div>
    <div class="an-row"><span class="an-label">Type</span>
      <span class="an-value" style="color:#ff9800">${{kindFull}}</span></div>
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">Entry Price</span>
      <span class="an-value">${{fmt(s.bp)}}</span></div>
    <div class="an-row"><span class="an-label">Stop Loss</span>
      <span class="an-value red">${{fmt(s.sl)}}
        <span style="font-size:10px;opacity:.8">${{fmtPct(s.sl_pct)}}</span></span></div>
    <div class="an-row"><span class="an-label">TP1 (${{D.tp1_mult}}×ATR)</span>
      <span class="an-value green">${{fmt(s.tp1)}}
        <span style="font-size:10px;opacity:.8">+${{s.tp1_pct?.toFixed(2)}}%</span></span></div>
    <div class="an-row"><span class="an-label">TP2 (${{D.tp2_mult}}×ATR)</span>
      <span class="an-value" style="color:#00b862">${{fmt(s.tp2)}}
        <span style="font-size:10px;opacity:.8">+${{s.tp2_pct?.toFixed(2)}}%</span></span></div>
    <div class="an-row"><span class="an-label">Risk/Reward</span>
      <span class="an-value yellow">1 : ${{s.rr ?? '—'}}</span></div>
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">ATR</span>
      <span class="an-value">฿${{s.atr}}</span></div>
    <div class="an-row"><span class="an-label">RSM</span>
      <span class="an-value ${{s.rsm_ok ? 'green' : 'yellow'}}">${{s.rsm?.toFixed(1)}}
        <span style="font-size:10px;opacity:.7">${{s.rsm_ok ? '✓' : '< '+D.rsm_min}}</span></span></div>
    <div class="an-row"><span class="an-label">RVol</span>
      <span class="an-value ${{s.rvol_ok ? 'green' : 'blue'}}">${{s.rvol?.toFixed(2)}}×
        <span style="font-size:10px;opacity:.7">${{s.rvol_ok ? '✓' : '< '+D.rvol_min+'x'}}</span></span></div>
    <div class="an-row"><span class="an-label">Regime (>SMA50)</span>
      <span class="an-value ${{s.regime_ok ? 'green' : 'grey'}}">${{s.regime_ok ? 'YES ✓' : 'NO ✗'}}</span></div>
    <div class="an-sep"></div>
    <div class="filter-row">
      <span class="badge ${{s.regime_ok?'pass':'fail'}}">REGIME</span>
      <span class="badge ${{s.rvol_ok?'pass':'fail'}}">RVOL</span>
      <span class="badge ${{s.rsm_ok?'pass':'fail'}}">RSM</span>
    </div>
  `;
}}

// ── Canvas click → find nearest signal ───────────────────────────────────
document.getElementById('cv-overlay').addEventListener('click', e => {{
  const rect = e.target.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  let best = null, bestDist = 18;
  D.signals.forEach((s,idx) => {{
    const x = xOf(s.i);
    const y = yOf(s.bar_y,0) - 10;
    const dist = Math.sqrt((mx-x)**2 + (my-y)**2);
    if(dist < bestDist) {{ bestDist=dist; best=idx; }}
  }});
  if(best != null) selectSignal(best);
}});

// ── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('resize', resize);
buildSignalList();
resize();
</script>
</body>
</html>"""

    safe  = ticker.replace('.', '_').replace('=', '_')
    fname = f'{safe}_{date_str}.html'
    path  = os.path.join(charts_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  Interactive chart: {fname}')
    return fname