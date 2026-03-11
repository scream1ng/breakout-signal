"""
chart_combined.py — Single self-contained HTML with all scanned stocks
  generate_combined_html(stocks_data, results, charts_dir, date_str) -> filename

  stocks_data : list of dicts from chart_interactive.get_chart_data()
  results     : list of run_ticker result dicts (for sidebar metadata)
"""

import os
import json


def generate_combined_html(
    stocks_data: list,
    results:     list,
    charts_dir:  str,
    date_str:    str,
    filename:    str = None,
) -> str:
    if not stocks_data:
        return None

    fname = filename or f'_combined_{date_str}.html'

    # Build metadata map: ticker → result dict
    meta_map = {r['ticker']: r for r in results}

    # Split into 3 groups, each sorted A→Z by ticker
    sig_stocks  = sorted([d for d in stocks_data if meta_map.get(d['ticker'],{}).get('today_signal')],
                         key=lambda d: d['ticker'])
    wtc_stocks  = sorted([d for d in stocks_data
                          if not meta_map.get(d['ticker'],{}).get('today_signal')
                          and meta_map.get(d['ticker'],{}).get('pending')],
                         key=lambda d: d['ticker'])
    rest_stocks = sorted([d for d in stocks_data
                          if not meta_map.get(d['ticker'],{}).get('today_signal')
                          and not meta_map.get(d['ticker'],{}).get('pending')],
                         key=lambda d: d['ticker'])

    # Rebuild stocks_data in section order so JS index matches
    stocks_data = sig_stocks + wtc_stocks + rest_stocks
    all_stocks_json = json.dumps(stocks_data)

    n_sig = len(sig_stocks)
    n_wtc = len(wtc_stocks)
    total = len(stocks_data)

    def _sb_item(idx, d, section):
        m       = meta_map.get(d['ticker'], {})
        rsm     = d.get('rsm_now', 0) or 0
        pnl_pct = m.get('total_pnl_pct', 0) or 0
        trades  = m.get('total_trades', 0) or 0
        rvol     = d.get('rvol_now', 0) or 0
        rvol_min = d.get('rvol_min', 1.5) or 1.5
        pnl_col  = '#00e676' if pnl_pct >= 0 else '#ef5350'
        pnl_str  = f'{pnl_pct:+.1f}%' if trades else '—'
        rvol_str = f'{rvol:.1f}x' if rvol else '—'
        rvol_col = '#00e676' if rvol >= rvol_min else 'var(--text)'
        # section: 'sig' | 'wtc' | ''
        item_cls = f'sb-item sb-{section}' if section else 'sb-item'
        return f"""
        <div class="{item_cls}" id="sb-{idx}" onclick="loadStock({idx})">
          <div class="sb-top">
            <span class="sb-ticker">{d['ticker'].replace('.BK','')}</span>
            <span class="sb-rsm">RSM {rsm:.0f}</span>
          </div>
          <div class="sb-bot">
            <span class="sb-rvol" style="color:{rvol_col}">RVol {rvol_str}</span>
            <span class="sb-pnl" style="color:{pnl_col}">{pnl_str}</span>
          </div>
        </div>"""

    sidebar_parts = []

    # ── Section 1: BREAKOUT ──────────────────────────────────────────────
    if sig_stocks:
        sidebar_parts.append(
            f'<div class="sb-section-hdr sb-hdr-sig">▲ BREAKOUT ({n_sig})</div>')
        for i, d in enumerate(sig_stocks):
            sidebar_parts.append(_sb_item(i, d, 'sig'))

    # ── Section 2: WATCHLIST ─────────────────────────────────────────────
    if wtc_stocks:
        sidebar_parts.append(
            f'<div class="sb-section-hdr sb-hdr-wtc"> WATCHLIST ({n_wtc})</div>')
        for i, d in enumerate(wtc_stocks, len(sig_stocks)):
            sidebar_parts.append(_sb_item(i, d, 'wtc'))

    # ── Section 3: Rest (no badge) ───────────────────────────────────────
    if rest_stocks:
        sidebar_parts.append(
            f'<div class="sb-section-hdr" style="color:var(--text)">ALL STOCKS ({len(rest_stocks)})</div>')
        for i, d in enumerate(rest_stocks, n_sig + n_wtc):
            sidebar_parts.append(_sb_item(i, d, ''))

    sidebar_html = '\n'.join(sidebar_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PB Scanner — Combined Chart [{date_str.replace('_','-')}]</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@600;700;800&display=swap');
  :root {{
    --bg:#131722; --panel:#1e222d; --border:#2a2e39; --text:#9598a1;
    --white:#d1d4dc; --accent:#00e5cc; --green:#00e676; --red:#ef5350;
    --yellow:#ffd740; --blue:#2196F3; --orange:#ff9800; --pink:#ff6ec7;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  html,body {{ height:100%; background:var(--bg); color:var(--white);
               font-family:'DM Mono',monospace; overflow:hidden; }}

  /* ── Layout ── */
  .app {{ display:grid; grid-template-columns:220px 1fr 300px;
          grid-template-rows:48px 1fr; height:100vh; }}
  header {{ grid-column:1/-1; display:flex; align-items:center; gap:14px;
            padding:0 18px; background:var(--panel);
            border-bottom:1px solid var(--border); }}
  .logo   {{ font-family:'Syne',sans-serif; font-weight:800; font-size:15px;
             letter-spacing:.08em; color:var(--accent); }}
  .hticker{{ font-family:'Syne',sans-serif; font-weight:700; font-size:16px; color:var(--white); }}
  .hinfo  {{ font-size:11px; color:var(--text); }}
  .hrsm   {{ margin-left:auto; font-size:12px; color:var(--yellow); font-weight:500; }}
  .hdate  {{ font-size:10px; color:var(--text); margin-left:12px; }}

  /* ── Sidebar ── */
  .sidebar {{ background:var(--panel); border-right:1px solid var(--border);
              display:flex; flex-direction:column; overflow:hidden; }}
  .sb-head {{ padding:10px 10px 6px; border-bottom:1px solid var(--border); flex-shrink:0; }}
  .sb-stats{{ font-size:9.5px; color:var(--text); margin-bottom:6px; }}
  .sb-stats span {{ color:var(--white); }}
  .sb-search {{ width:100%; background:#0d1117; border:1px solid var(--border);
                color:var(--white); padding:5px 8px; font-family:'DM Mono',monospace;
                font-size:11px; border-radius:4px; outline:none; }}
  .sb-search:focus {{ border-color:var(--accent); }}
  .sb-list {{ flex:1; overflow-y:auto; }}
  .sb-list::-webkit-scrollbar {{ width:3px; }}
  .sb-list::-webkit-scrollbar-thumb {{ background:var(--border); }}

  /* ── Sidebar section headers ── */
  .sb-section-hdr {{
    padding:7px 10px 5px; font-size:9px; font-weight:700; letter-spacing:.1em;
    text-transform:uppercase; border-bottom:1px solid var(--border);
    background:rgba(0,0,0,.25);
  }}
  .sb-hdr-sig {{ color:var(--pink);   background:rgba(255,110,199,.07); border-left:3px solid var(--pink); }}
  .sb-hdr-wtc {{ color:var(--yellow); background:rgba(255,215,64,.05);  border-left:3px solid var(--yellow); }}

  /* ── Sidebar items ── */
  .sb-item {{ padding:7px 10px 7px 12px; cursor:pointer;
              border-bottom:1px solid rgba(42,46,57,.5);
              transition:background .1s; border-left:3px solid transparent; }}
  .sb-item:hover   {{ background:rgba(0,229,204,.05); }}
  .sb-item.active  {{ background:rgba(0,229,204,.12); border-left-color:var(--accent); }}
  .sb-sig          {{ border-left-color:rgba(255,110,199,.4); background:rgba(255,110,199,.04); }}
  .sb-sig.active   {{ border-left-color:var(--pink); background:rgba(255,110,199,.1); }}
  .sb-wtc          {{ border-left-color:rgba(255,215,64,.35); background:rgba(255,215,64,.03); }}
  .sb-wtc.active   {{ border-left-color:var(--yellow); background:rgba(255,215,64,.09); }}
  .sb-top {{ display:flex; justify-content:space-between; align-items:baseline; }}
  .sb-bot {{ display:flex; justify-content:space-between; margin-top:3px; }}
  .sb-ticker {{ font-family:'Syne',sans-serif; font-weight:700; font-size:12px; color:var(--white); }}
  .sb-rsm    {{ font-size:10px; color:var(--yellow); }}
  .sb-rvol   {{ font-size:9px; color:var(--text); }}
  .sb-pnl    {{ font-size:10px; font-weight:500; }}

  /* ── Tabs ── */
  .tab-bar {{ display:flex; border-bottom:1px solid var(--border); flex-shrink:0; background:var(--panel); }}
  .tab {{ flex:1; padding:9px 0; text-align:center; font-size:10px; letter-spacing:.06em;
          cursor:pointer; color:var(--text); border-bottom:2px solid transparent; transition:all .15s; }}
  .tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
  .tab-pane {{ display:none; flex:1; flex-direction:column; overflow:hidden; }}
  .tab-pane.active {{ display:flex; }}
  /* ── Trade table ── */
  .trade-table {{ flex:1; overflow-y:auto; font-size:10px; }}
  .trade-table::-webkit-scrollbar {{ width:3px; }}
  .trade-table::-webkit-scrollbar-thumb {{ background:var(--border); }}
  .tr-hdr {{ display:grid; grid-template-columns:72px 72px 56px 44px 1fr;
             gap:2px; padding:6px 8px; color:var(--text);
             border-bottom:1px solid var(--border); font-size:9px; letter-spacing:.05em;
             position:sticky; top:0; background:var(--panel); z-index:1; }}
  .tr-row {{ display:grid; grid-template-columns:72px 72px 56px 44px 1fr;
             gap:2px; padding:5px 8px; border-bottom:1px solid rgba(42,46,57,.4);
             cursor:pointer; transition:background .1s; align-items:center; }}
  .tr-row:hover  {{ background:rgba(0,229,204,.05); }}
  .tr-row.active {{ background:rgba(0,229,204,.1); }}
  .tr-filter {{ font-size:8px; padding:1px 5px; border-radius:3px; font-weight:600; }}
  .tf-full   {{ background:rgba(255,110,199,.15); color:#ff6ec7; }}
  .tf-norsm  {{ background:rgba(33,150,243,.15);  color:#64b5f6; }}
  .tf-regime {{ background:rgba(158,158,158,.15); color:#aaa; }}
  .tr-stat {{ padding:8px 10px; font-size:10px; border-top:1px solid var(--border);
              display:flex; gap:10px; flex-wrap:wrap; flex-shrink:0; color:var(--text); }}
  /* ── Trade summary ── */
  .trade-summary {{ border-top:1px solid var(--border); padding:10px 12px;
                    font-size:10px; flex-shrink:0; }}
  .ts-title {{ color:var(--text); font-size:9px; letter-spacing:.06em;
               text-transform:uppercase; margin-bottom:6px; }}
  .ts-row {{ display:flex; justify-content:space-between; align-items:center;
             padding:3px 0; border-bottom:1px solid rgba(42,46,57,.4); }}
  .ts-row:last-child {{ border-bottom:none; }}
  /* ── Chart area ── */
  .chart-area {{ position:relative; overflow:hidden; background:var(--bg); }}
  canvas {{ position:absolute; top:0; left:0; }}
  .no-stock {{ display:flex; align-items:center; justify-content:center;
               height:100%; color:var(--text); font-size:13px; opacity:.5; }}

  /* ── Signal panel (right) ── */
  .panel {{ background:var(--panel); border-left:1px solid var(--border);
            overflow-y:auto; display:flex; flex-direction:column; }}
  .panel::-webkit-scrollbar {{ width:4px; }}
  .panel::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:2px; }}
  .sig-header {{ padding:12px 14px 8px; border-bottom:1px solid var(--border);
                 font-size:11px; color:var(--text); letter-spacing:.06em; flex-shrink:0; }}
  .sig-list {{ flex:1; overflow-y:auto; }}
  .sig-item {{ padding:9px 14px; cursor:pointer; border-bottom:1px solid var(--border);
               transition:background .12s; display:flex; align-items:center; gap:10px; }}
  .sig-item:hover  {{ background:rgba(0,229,204,.06); }}
  .sig-item.active {{ background:rgba(0,229,204,.13); border-left:2px solid var(--accent); }}
  .sig-dot  {{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }}
  .sig-info {{ flex:1; }}
  .sig-date {{ font-size:11px; color:var(--white); font-weight:500; }}
  .sig-sub  {{ font-size:10px; color:var(--text); margin-top:1px; }}

  .analysis {{ border-top:1px solid var(--border); padding:14px; flex-shrink:0; }}
  .an-title {{ font-family:'Syne',sans-serif; font-weight:700; font-size:13px;
               color:var(--accent); margin-bottom:10px; letter-spacing:.04em; }}
  .an-row   {{ display:flex; justify-content:space-between; align-items:center;
               padding:4px 0; border-bottom:1px solid var(--border); font-size:11px; }}
  .an-row:last-child {{ border-bottom:none; }}
  .an-label {{ color:var(--text); }}
  .an-value {{ color:var(--white); font-weight:500; text-align:right; }}
  .an-value.green  {{ color:var(--green);  }}
  .an-value.red    {{ color:var(--red);    }}
  .an-value.yellow {{ color:var(--yellow); }}
  .an-value.blue   {{ color:var(--blue);   }}
  .an-value.grey   {{ color:#888; }}
  .an-sep {{ height:1px; background:var(--border); margin:8px 0; }}
  .an-empty{{ color:var(--text); font-size:11px; text-align:center; padding:20px 0; opacity:.6; }}
  .filter-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }}
  .badge {{ font-size:9.5px; padding:2px 8px; border-radius:10px;
            font-weight:600; letter-spacing:.04em; }}
  .badge.pass {{ background:rgba(0,230,118,.15); color:var(--green); border:1px solid rgba(0,230,118,.3); }}
  .badge.fail {{ background:rgba(239,83,80,.15);  color:var(--red);   border:1px solid rgba(239,83,80,.3); }}
  .legend {{ display:flex; gap:12px; flex-wrap:wrap; padding:6px 18px;
             background:var(--panel); border-top:1px solid var(--border);
             font-size:10px; color:var(--text); }}
  .leg-item {{ display:flex; align-items:center; gap:5px; }}
  .leg-dot  {{ width:8px; height:8px; border-radius:50%; }}
  kbd {{ background:#2a2e39; border:1px solid #444; border-radius:3px;
         padding:0 5px; font-size:10px; color:var(--text); }}
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">⬡ PB SCANNER</div>
    <div class="hticker" id="h-ticker">← Select a stock</div>
    <div class="hinfo"   id="h-info"></div>
    <div class="hrsm"    id="h-rsm"></div>
    <div class="hdate">{date_str.replace('_','-')} · {total} stocks · <span style="color:var(--pink)">{n_sig} signals</span> · <span style="color:var(--yellow)">{n_wtc} watching</span></div>
    <div style="margin-left:8px;font-size:10px;color:var(--text)">
      <kbd>↑↓</kbd> navigate &nbsp; <kbd>Esc</kbd> clear
    </div>
  </header>

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sb-head">
      <div class="sb-stats">
        <span>{total}</span> stocks &nbsp;·&nbsp;
        <span style="color:var(--pink)">{n_sig}</span> signals &nbsp;·&nbsp;
        <span style="color:var(--yellow)">{n_wtc}</span> watching
      </div>
      <input class="sb-search" id="sb-search" type="text"
             placeholder="Search ticker..." oninput="filterSidebar(this.value)">
    </div>
    <div class="sb-list" id="sb-list">
      {sidebar_html}
    </div>
  </div>

  <!-- Canvas chart -->
  <div class="chart-area" id="chart-area">
    <canvas id="cv-bg"></canvas>
    <canvas id="cv-main"></canvas>
    <canvas id="cv-overlay"></canvas>
    <div class="no-stock" id="no-stock">← Select a stock from the sidebar</div>
  </div>

  <!-- Signal panel -->
  <div class="panel">
    <div class="sig-header">
      SIGNALS — <span id="sig-count" style="color:var(--white)">—</span>
      <span id="sig-filter-info" style="font-size:10px;display:block;margin-top:2px;opacity:.7"></span>
    </div>
    <div class="sig-list" id="sig-list"></div>
    <div class="analysis" id="analysis">
      <div class="an-empty">← Click a signal to analyse</div>
    </div>
    <div class="trade-summary" id="trade-summary"></div>
  </div>
</div>

<script>
// ── All stock data ─────────────────────────────────────────────────────────────
const ALL_STOCKS = {all_stocks_json};
let D = null;
let currentStockIdx = null;
let selectedSigIdx  = null;

// ── Load a stock ──────────────────────────────────────────────────────────────
function loadStock(idx) {{
  if(currentStockIdx != null)
    document.getElementById('sb-'+currentStockIdx)?.classList.remove('active');

  currentStockIdx = idx;
  D = ALL_STOCKS[idx];

  document.getElementById('sb-'+idx)?.classList.add('active');
  document.getElementById('sb-'+idx)?.scrollIntoView({{block:'nearest'}});
  document.getElementById('no-stock').style.display = 'none';

  selectedSigIdx = null;
  document.getElementById('trade-summary').innerHTML = '';
  resize();
  buildSignalList();
  document.getElementById('analysis').innerHTML = '<div class="an-empty">← Click a signal to analyse</div>';
}}

// ── Sidebar search/filter ──────────────────────────────────────────────────────
function filterSidebar(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.sb-item').forEach(el => {{
    const ticker = el.querySelector('.sb-ticker')?.textContent.toLowerCase() || '';
    el.style.display = ticker.includes(q) ? '' : 'none';
  }});
}}

// ── Keyboard navigation ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {{
  if(e.key === 'Escape') {{
    document.getElementById('sb-search').value = '';
    filterSidebar('');
    return;
  }}
  if(e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
    e.preventDefault();
    const visible = [...document.querySelectorAll('.sb-item')]
      .filter(el => el.style.display !== 'none')
      .map(el => parseInt(el.id.replace('sb-','')));
    if(!visible.length) return;
    const cur = currentStockIdx;
    const pos = visible.indexOf(cur);
    const next = e.key === 'ArrowDown'
      ? visible[Math.min(pos+1, visible.length-1)]
      : visible[Math.max(pos-1, 0)];
    if(next !== cur) loadStock(next);
  }}
}});

// ── Chart geometry ─────────────────────────────────────────────────────────────
const MARGIN = {{l:8, r:72, t:8, b:28}};
let W, H, BAR_W, X0, PRICE_MIN, PRICE_MAX, PRICE_RANGE;
let panelHeights;

function resize() {{
  if(!D) return;
  const el = document.getElementById('chart-area');
  W = el.clientWidth; H = el.clientHeight;
  ['cv-bg','cv-main','cv-overlay'].forEach(id => {{
    const c = document.getElementById(id);
    c.width = W; c.height = H;
  }});
  computeScales();
  drawAll();
  if(selectedSigIdx != null) drawOverlay(selectedSigIdx);
}}

function computeScales() {{
  const candles = D.candles;
  const N = candles.length;
  const pHMain = 0.62, pHRsm = 0.17, pHVol = 0.17;
  const totalH = H - MARGIN.t - MARGIN.b;
  panelHeights = [totalH * pHMain, totalH * pHRsm, totalH * pHVol];
  BAR_W = Math.max(1.5, (W - MARGIN.l - MARGIN.r) / (N + 4));
  X0    = MARGIN.l + BAR_W * 2;
  let lo = Infinity, hi = -Infinity;
  candles.forEach(c => {{ if(c.h > hi) hi = c.h; if(c.l < lo) lo = c.l; }});
  [D.ema10, D.sma50, D.sma200].forEach(arr => arr && arr.forEach(v => {{
    if(v != null) {{ if(v>hi) hi=v; if(v<lo) lo=v; }}
  }}));
  const pad = (hi - lo) * 0.08;
  PRICE_MIN = lo - pad; PRICE_MAX = hi + pad;
  PRICE_RANGE = PRICE_MAX - PRICE_MIN;
}}

function xOf(i)  {{ return X0 + i * BAR_W; }}
function yOf(p, panel=0) {{
  const panelTop = MARGIN.t + panelHeights.slice(0, panel).reduce((a,b)=>a+b, 0);
  const panelH   = panelHeights[panel];
  let mn, mx;
  if(panel === 0)      {{ mn = PRICE_MIN; mx = PRICE_MAX; }}
  else if(panel === 1) {{ mn = 0; mx = 100; }}
  else {{
    mn = 0;
    mx = Math.max(...D.rvol.filter(v=>v!=null)) * 1.1;
    if(mx < D.rvol_min * 2) mx = D.rvol_min * 2;
  }}
  return panelTop + panelH - (p - mn) / (mx - mn) * panelH;
}}
function panelTopY(p) {{
  return MARGIN.t + panelHeights.slice(0,p).reduce((a,b)=>a+b,0);
}}

// ── Drawing ────────────────────────────────────────────────────────────────────
function drawAll() {{
  drawBackground();
  drawChart();
}}

function drawBackground() {{
  const cv = document.getElementById('cv-bg');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);
  const candles = D.candles; const N = candles.length;

  [0,1,2].forEach(p => {{
    ctx.fillStyle = p % 2 === 0 ? '#131722' : '#111520';
    const pt = panelTopY(p);
    ctx.fillRect(MARGIN.l, pt, W-MARGIN.l-MARGIN.r, panelHeights[p]);
  }});

  ctx.strokeStyle = '#2a2e39'; ctx.lineWidth = 0.4;
  const steps = 6;
  for(let k=0; k<=steps; k++) {{
    const p = PRICE_MIN + (PRICE_MAX - PRICE_MIN) * k / steps;
    const y = yOf(p, 0);
    ctx.beginPath(); ctx.moveTo(MARGIN.l, y); ctx.lineTo(W-MARGIN.r, y); ctx.stroke();
    ctx.fillStyle = '#9598a1'; ctx.font = '10px DM Mono'; ctx.textAlign='left';
    ctx.fillText(p.toFixed(2), W-MARGIN.r+3, y+3);
  }}

  [25,50,75].forEach(v => {{
    const y = yOf(v,1);
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
  }});

  let pm = -1;
  candles.forEach((c,i) => {{
    const d = new Date(c.d);
    if(d.getMonth() !== pm) {{
      pm = d.getMonth();
      const x = xOf(i);
      ctx.fillStyle = '#9598a1'; ctx.font = '9px DM Mono'; ctx.textAlign='center';
      const lbl = d.toLocaleDateString('en',{{month:'short'}}) +
                  (d.getMonth()===0 ? ' '+d.getFullYear() : '');
      ctx.fillText(lbl, x, H - MARGIN.b + 12);
    }}
  }});

  [1,2].forEach(p => {{
    const y = panelTopY(p);
    ctx.strokeStyle = '#2a2e39'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
  }});

  ctx.fillStyle='#ffd740'; ctx.font='9px DM Mono'; ctx.textAlign='right';
  ctx.fillText('RSM',          W-MARGIN.r+68, panelTopY(1)+12);
  ctx.fillText(D.rvol_min+'x', W-MARGIN.r+68, panelTopY(2)+12);
}}

function drawChart() {{
  const cv  = document.getElementById('cv-main');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);
  const candles = D.candles;

  const drawLines = (arr, col, lw, dash=[]) => {{
    if(!arr) return;
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

  const bw = Math.max(1, BAR_W * 0.55);
  candles.forEach((c,i) => {{
    const x = xOf(i);
    ctx.strokeStyle = c.col; ctx.lineWidth=0.8;
    ctx.beginPath(); ctx.moveTo(x,yOf(c.h,0)); ctx.lineTo(x,yOf(c.l,0)); ctx.stroke();
    const yO=yOf(c.o,0); const yC=yOf(c.c,0);
    const bTop=Math.min(yO,yC); const bH=Math.max(Math.abs(yO-yC),1.5);
    ctx.fillStyle=c.col; ctx.fillRect(x-bw/2, bTop, bw, bH);
  }});

  const drawMA = (arr, col, lw, dash=[]) => {{
    if(!arr) return;
    ctx.strokeStyle=col; ctx.lineWidth=lw; ctx.setLineDash(dash);
    let started=false; ctx.beginPath();
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

  D.signals.forEach((s,idx) => {{
    const x=xOf(s.i); const topY=yOf(s.bar_y,0); const y=topY-10;
    ctx.fillStyle=s.col;
    ctx.beginPath(); ctx.arc(x,y,5,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle='#131722'; ctx.lineWidth=1; ctx.stroke();
  }});

  // ── Exit arrows ──────────────────────────────────────────────────────
  function drawArrow(bar, price, col, sz=7) {{
    if(bar==null || bar<0 || bar>=candles.length) return;
    const x=xOf(bar), y=yOf(price,0)-sz-4;
    ctx.fillStyle=col;
    ctx.beginPath();
    ctx.moveTo(x, y+sz); ctx.lineTo(x-sz*0.7, y); ctx.lineTo(x+sz*0.7, y);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle='#131722'; ctx.lineWidth=0.8; ctx.stroke();
  }}
  if(D.trades) D.trades.forEach(t => {{
    if(t.tp1_hit && t.tp1_bar!=null) drawArrow(t.tp1_bar, candles[t.tp1_bar]?.h, '#00e676', 6);
    if(t.tp2_hit && t.tp2_bar!=null) drawArrow(t.tp2_bar, candles[t.tp2_bar]?.h, '#00b862', 6);
    const exitCol = t.exit_reason==='SL' ? '#ef5350'
                  : t.exit_reason==='EMA10' ? '#ffd740' : '#888';
    if(t.exit_bar!=null) drawArrow(t.exit_bar, candles[t.exit_bar]?.h, exitCol, 7);
  }});

  const lc = D.last_close;
  const ly = yOf(lc,0);
  ctx.fillStyle='#ef5350';
  ctx.fillRect(W-MARGIN.r+1, ly-8, MARGIN.r-2, 16);
  ctx.fillStyle='white'; ctx.font='bold 10px DM Mono'; ctx.textAlign='center';
  ctx.fillText(lc.toFixed(2), W-MARGIN.r+MARGIN.r/2, ly+4);

  ctx.strokeStyle='#ffd740'; ctx.lineWidth=1.1; ctx.setLineDash([]);
  let started=false; ctx.beginPath();
  D.rsm.forEach((v,i) => {{
    if(v==null){{started=false;return;}}
    const x=xOf(i); const y=yOf(v,1);
    if(!started){{ctx.moveTo(x,y);started=true;}}else{{ctx.lineTo(x,y);}}
  }});
  ctx.stroke();
  ctx.strokeStyle='rgba(255,215,64,.5)'; ctx.lineWidth=0.8; ctx.setLineDash([4,3]);
  const yRsmMin=yOf(D.rsm_min,1);
  ctx.beginPath(); ctx.moveTo(MARGIN.l,yRsmMin); ctx.lineTo(W-MARGIN.r,yRsmMin); ctx.stroke();
  ctx.setLineDash([]);

  D.rvol.forEach((v,i) => {{
    const c = candles[i];
    const col = v >= D.rvol_min ? '#26a69a' : '#3a3a3a';
    const x=xOf(i); const y=yOf(v,2); const base=yOf(0,2);
    ctx.fillStyle=col; ctx.fillRect(x-BAR_W*0.4, y, BAR_W*0.8, base-y);
    if(D.gaps && D.gaps[i]) {{
      ctx.fillStyle='#ffd740';
      ctx.beginPath(); ctx.arc(x, y-4, 2.5, 0, Math.PI*2); ctx.fill();
    }}
  }});
  ctx.strokeStyle='rgba(255,152,0,.7)'; ctx.lineWidth=0.9; ctx.setLineDash([4,3]);
  const yVolMin=yOf(D.rvol_min,2);
  ctx.beginPath(); ctx.moveTo(MARGIN.l,yVolMin); ctx.lineTo(W-MARGIN.r,yVolMin); ctx.stroke();
  ctx.setLineDash([]);
}}

function drawOverlay(sigIdx) {{
  const cv  = document.getElementById('cv-overlay');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);
  if(sigIdx == null || !D) return;
  const s = D.signals[sigIdx];
  const x = xOf(s.i);
  ctx.strokeStyle='rgba(0,229,204,.25)'; ctx.lineWidth=1; ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(x,MARGIN.t); ctx.lineTo(x,H-MARGIN.b); ctx.stroke();
  ctx.setLineDash([]);
  if(s.bp) {{
    const y=yOf(s.bp,0);
    ctx.strokeStyle='rgba(0,230,118,.4)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(MARGIN.l,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}
  if(s.sl) {{
    const y=yOf(s.sl,0);
    ctx.strokeStyle='rgba(239,83,80,.5)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle='rgba(239,83,80,.15)';
    ctx.fillRect(x, y, W-MARGIN.r-x, yOf(s.bp,0)-y);
  }}
  if(s.tp1) {{
    const y=yOf(s.tp1,0);
    ctx.strokeStyle='rgba(0,230,118,.5)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}
  if(s.tp2) {{
    const y=yOf(s.tp2,0);
    ctx.strokeStyle='rgba(0,200,100,.4)'; ctx.lineWidth=0.9; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(W-MARGIN.r,y); ctx.stroke();
    ctx.setLineDash([]);
  }}
  // Big circle with white border on entry
  ctx.fillStyle=s.col;
  ctx.beginPath(); ctx.arc(x, yOf(s.bar_y,0)-10, 7, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle='white'; ctx.lineWidth=1.5; ctx.stroke();

  // Highlight matching trade exit arrows
  // Try Full trade first, fall back to any trade at that bar
  const trade = (D.trades||[]).find(t => t.entry_bar === s.i && t.filter_type === 'Full')
             || (D.trades||[]).find(t => t.entry_bar === s.i);
  if(trade) {{
    function drawArrowHL(bar, price, col, sz=9) {{
      if(bar==null || bar<0 || bar>=D.candles.length) return;
      const ax=xOf(bar), ay=yOf(price,0)-sz-4;
      ctx.fillStyle=col;
      ctx.beginPath();
      ctx.moveTo(ax, ay+sz); ctx.lineTo(ax-sz*0.7, ay); ctx.lineTo(ax+sz*0.7, ay);
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle='white'; ctx.lineWidth=1.5; ctx.stroke();
    }}
    if(trade.tp1_hit && trade.tp1_bar!=null)
      drawArrowHL(trade.tp1_bar, D.candles[trade.tp1_bar]?.h, '#00e676', 9);
    if(trade.tp2_hit && trade.tp2_bar!=null)
      drawArrowHL(trade.tp2_bar, D.candles[trade.tp2_bar]?.h, '#00b862', 9);
    const exitCol = trade.exit_reason==='SL' ? '#ef5350'
                  : trade.exit_reason==='EMA10' ? '#ffd740' : '#888';
    if(trade.exit_bar!=null)
      drawArrowHL(trade.exit_bar, D.candles[trade.exit_bar]?.h, exitCol, 10);
  }}
}}

// ── Signal list (right panel) ──────────────────────────────────────────────────
function buildSignalList() {{
  document.getElementById('h-ticker').textContent = D.ticker;
  document.getElementById('h-info').textContent   = (D.desc||'') + '  ' + (D.sector||'');
  document.getElementById('h-rsm').textContent    = 'RSM ' + (D.rsm_now?.toFixed(0)||'—') + '  1D';
  document.getElementById('sig-count').textContent = D.signals.length;
  document.getElementById('sig-filter-info').textContent =
    `RVol>${{D.rvol_min}}x  RSM>${{D.rsm_min}}`;

  // Build lookup: entry_bar → trade (Full first, fallback any)
  const tradeByBar = {{}};
  (D.trades||[]).forEach(t => {{
    if(!tradeByBar[t.entry_bar] || t.filter_type==='Full') tradeByBar[t.entry_bar] = t;
  }});

  const list = document.getElementById('sig-list');
  list.innerHTML = '';
  D.signals.forEach((s, idx) => {{
    const el = document.createElement('div');
    el.className = 'sig-item';
    el.id = 'sig-' + idx;
    const kindLabel = s.kind === 'hz' ? 'Horiz' : 'TL';
    const trade = tradeByBar[s.i];
    let retHtml = '';
    if(trade) {{
      const retCol = trade.ret_pct >= 0 ? '#00e676' : '#ef5350';
      const tp1str = trade.tp1_hit ? ' TP1✓' : '';
      const tp2str = trade.tp2_hit ? ' TP2✓' : '';
      const rsn    = trade.exit_reason==='EMA10' ? 'MA10' : (trade.exit_reason||'');
      retHtml = ` <span style="color:${{retCol}};font-weight:600">${{trade.ret_pct>=0?'+':''}}${{trade.ret_pct.toFixed(1)}}%${{tp1str}}${{tp2str}} ${{rsn}}</span>`;
    }}
    el.innerHTML = `
      <div class="sig-dot" style="background:${{s.col}}"></div>
      <div class="sig-info">
        <div class="sig-date">${{s.date}} <span style="color:#888;font-size:9px">${{kindLabel}}</span></div>
        <div class="sig-sub">฿${{s.bp.toFixed(2)}} · ${{s.label}}${{retHtml}}</div>
      </div>`;
    el.onclick = () => selectSignal(idx);
    list.appendChild(el);
  }});

  buildTradeSummary();
}}

function buildTradeSummary() {{
  const box = document.getElementById('trade-summary');
  const trades = D.trades || [];
  if(!trades.length) {{ box.innerHTML=''; return; }}

  const fc = {{ 'Full':'tf-full', 'No RSM':'tf-norsm', 'Regime only':'tf-regime' }};
  const groups = {{}};
  trades.forEach(t => {{
    if(!groups[t.filter_type]) groups[t.filter_type]=[];
    groups[t.filter_type].push(t);
  }});

  let rows = '';
  ['Full','No RSM','Regime only'].forEach(lbl => {{
    const ts = groups[lbl]; if(!ts) return;
    const wins = ts.filter(t=>t.win).length;
    const wr   = (wins/ts.length*100).toFixed(0);
    const avg  = (ts.reduce((s,t)=>s+t.ret_pct,0)/ts.length);
    const avgCol = avg >= 0 ? '#00e676' : '#ef5350';
    rows += `<div class="ts-row">
      <span><span class="tr-filter ${{fc[lbl]||''}}" style="margin-right:5px">${{lbl}}</span>
        ${{ts.length}}T &nbsp; WR${{wr}}%</span>
      <span style="color:${{avgCol}};font-weight:600">avg ${{avg>=0?'+':''}}${{avg.toFixed(1)}}%</span>
    </div>`;
  }});

  box.innerHTML = `<div class="ts-title">BACKTEST SUMMARY</div>${{rows}}`;
}}

function selectSignal(idx) {{
  if(selectedSigIdx != null)
    document.getElementById('sig-'+selectedSigIdx)?.classList.remove('active');
  selectedSigIdx = idx;
  document.getElementById('sig-'+idx)?.classList.add('active');
  document.getElementById('sig-'+idx)?.scrollIntoView({{block:'nearest'}});
  drawOverlay(idx);
  renderAnalysis(idx);
}}

function renderAnalysis(idx) {{
  const s   = D.signals[idx];
  const box = document.getElementById('analysis');
  const fmt    = (v,d=2) => v!=null ? `฿${{v.toFixed(d)}}` : '—';
  const fmtPct = (v)     => v!=null ? (v>=0?'+':'')+v.toFixed(2)+'%' : '—';
  const kindFull = s.kind === 'hz' ? 'Horizontal Breakout' : 'Trendline Breakout';
  box.innerHTML = `
    <div class="an-title">SIGNAL ANALYSIS</div>
    <div class="an-row"><span class="an-label">Date</span><span class="an-value">${{s.date}}</span></div>
    <div class="an-row"><span class="an-label">Type</span>
      <span class="an-value" style="color:#ff9800">${{kindFull}}</span></div>
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">Entry Price</span>
      <span class="an-value">${{fmt(s.bp)}}</span></div>
    <div class="an-row"><span class="an-label">Stop Loss</span>
      <span class="an-value red">${{fmt(s.sl)}} <span style="font-size:10px;opacity:.8">${{fmtPct(s.sl_pct)}}</span></span></div>
    <div class="an-row"><span class="an-label">TP1 (${{D.tp1_mult}}×ATR)</span>
      <span class="an-value green">${{fmt(s.tp1)}} <span style="font-size:10px;opacity:.8">+${{s.tp1_pct?.toFixed(2)}}%</span></span></div>
    <div class="an-row"><span class="an-label">TP2 (${{D.tp2_mult}}×ATR)</span>
      <span class="an-value" style="color:#00b862">${{fmt(s.tp2)}} <span style="font-size:10px;opacity:.8">+${{s.tp2_pct?.toFixed(2)}}%</span></span></div>
    <div class="an-row"><span class="an-label">Risk/Reward</span>
      <span class="an-value yellow">1 : ${{s.rr??'—'}}</span></div>
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">ATR</span><span class="an-value">฿${{s.atr}}</span></div>
    <div class="an-row"><span class="an-label">RSM</span>
      <span class="an-value ${{s.rsm_ok?'green':'yellow'}}">${{s.rsm?.toFixed(1)}}
        <span style="font-size:10px;opacity:.7">${{s.rsm_ok?'✓':'< '+D.rsm_min}}</span></span></div>
    <div class="an-row"><span class="an-label">RVol</span>
      <span class="an-value ${{s.rvol_ok?'green':'blue'}}">${{s.rvol?.toFixed(2)}}×
        <span style="font-size:10px;opacity:.7">${{s.rvol_ok?'✓':'< '+D.rvol_min+'x'}}</span></span></div>
    <div class="an-row"><span class="an-label">Regime (>SMA50)</span>
      <span class="an-value ${{s.regime_ok?'green':'grey'}}">${{s.regime_ok?'YES ✓':'NO ✗'}}</span></div>
    <div class="an-sep"></div>
    <div class="filter-row">
      <span class="badge ${{s.regime_ok?'pass':'fail'}}">REGIME</span>
      <span class="badge ${{s.rvol_ok?'pass':'fail'}}">RVOL</span>
      <span class="badge ${{s.rsm_ok?'pass':'fail'}}">RSM</span>
    </div>`;
}}

// ── Canvas click → nearest signal
document.getElementById('cv-overlay').addEventListener('click', e => {{
  if(!D) return;
  const rect = e.target.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  let best=null, bestDist=18;
  D.signals.forEach((s,idx) => {{
    const x=xOf(s.i); const y=yOf(s.bar_y,0)-10;
    const dist=Math.sqrt((mx-x)**2+(my-y)**2);
    if(dist < bestDist){{ bestDist=dist; best=idx; }}
  }});
  if(best != null) selectSignal(best);
}});

window.addEventListener('resize', resize);

// Auto-select first stock with today's signal, else first stock
const firstSignal = ALL_STOCKS.findIndex(d => d.signals.some(s => s.col === '#ff6ec7'));
loadStock(firstSignal >= 0 ? firstSignal : 0);
</script>
</body>
</html>"""

    path = os.path.join(charts_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path