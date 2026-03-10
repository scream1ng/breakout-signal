#!/usr/bin/env python3
"""
Chart Viewer — local web server for browsing interactive swing trader charts.
Run: python viewer.py
Open: http://localhost:8765

Each chart is an interactive HTML file. Click any signal dot to see:
  Entry price, SL, TP1, TP2, RSM, RVol, Risk/Reward, filter status.

Colour coding on signal dots:
  Green  — all gates pass (regime + RVol + RSM)
  Yellow — RSM fails
  Blue   — RVol fails
  Grey   — below SMA50
"""

import os, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CHARTS_DIR = Path(__file__).parent / 'charts'
PORT = 8765


def get_charts():
    """Return list of chart dicts, preferring .html over .png."""
    seen   = {}   # ticker_date -> dict
    # Collect html files first (interactive), then png as fallback
    for ext in ('html', 'png'):
        for f in sorted(CHARTS_DIR.glob(f'*.{ext}'), reverse=True):
            name  = f.stem
            parts = name.split('_')
            if len(parts) < 4: continue   # need at least TICKER_YYYY_MM_DD
            date_str = '-'.join(parts[-3:])
            ticker   = '_'.join(parts[:-3])
            key      = name   # stem is unique per ticker+date
            if key not in seen:
                seen[key] = {
                    'file':       f.name,
                    'html_file':  f.name if ext == 'html' else None,
                    'png_file':   f.name if ext == 'png'  else None,
                    'ticker':     ticker,
                    'date':       date_str,
                    'name':       name,
                    'interactive': ext == 'html',
                }
            else:
                # Fill in the other format
                if ext == 'png' and seen[key]['png_file'] is None:
                    seen[key]['png_file'] = f.name
                elif ext == 'html' and seen[key]['html_file'] is None:
                    seen[key]['html_file'] = f.name
                    seen[key]['interactive'] = True
                    seen[key]['file'] = f.name

    return sorted(seen.values(), key=lambda x: x['name'], reverse=True)


SHELL = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Swing Trader · Chart Viewer</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@600;700;800&display=swap');
  :root {
    --bg:#0a0c0f; --panel:#10141a; --border:#1e2530;
    --accent:#00e5cc; --text:#c8d0dc; --muted:#4a5568;
    --green:#26a69a; --red:#ef5350;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  html,body { height:100%; background:var(--bg); color:var(--text);
              font-family:'DM Mono',monospace; overflow:hidden; }
  .app { display:grid; grid-template-columns:240px 1fr;
         grid-template-rows:50px 1fr; height:100vh; }

  header { grid-column:1/-1; display:flex; align-items:center; gap:14px;
           padding:0 18px; background:var(--panel);
           border-bottom:1px solid var(--border); }
  .logo  { font-family:'Syne',sans-serif; font-weight:800; font-size:14px;
           letter-spacing:.08em; color:var(--accent); }
  .sep   { width:1px; height:22px; background:var(--border); }
  .hinfo { font-size:10px; color:var(--muted); }
  .hcount{ margin-left:auto; font-size:10px; color:var(--muted); }
  input  { background:var(--bg); border:1px solid var(--border); border-radius:4px;
           color:var(--text); font-family:inherit; font-size:11px;
           padding:5px 10px; outline:none; width:140px; transition:border-color .2s; }
  input:focus { border-color:var(--accent); }

  .sidebar { background:var(--panel); border-right:1px solid var(--border);
             overflow-y:auto; }
  .sidebar::-webkit-scrollbar { width:3px; }
  .sidebar::-webkit-scrollbar-thumb { background:var(--border); border-radius:2px; }

  .item { display:flex; align-items:center; gap:8px; padding:9px 12px;
          cursor:pointer; border-bottom:1px solid var(--border); transition:background .12s; }
  .item:hover  { background:rgba(0,229,204,.04); }
  .item.active { background:rgba(0,229,204,.12); border-left:2px solid var(--accent); }
  .item.hidden { display:none; }
  .idx    { font-size:9px; color:var(--muted); min-width:20px; text-align:right; }
  .iinfo  { flex:1; overflow:hidden; }
  .iticker{ font-family:'Syne',sans-serif; font-weight:700; font-size:12px; color:#fff; }
  .idate  { font-size:9px; color:var(--muted); margin-top:1px; }
  .ibadge { font-size:8px; padding:1px 5px; border-radius:8px; margin-left:4px;
            background:rgba(0,229,204,.15); color:var(--accent); border:1px solid rgba(0,229,204,.3); }

  .main { display:flex; flex-direction:column; overflow:hidden; background:var(--bg); }

  .nav { display:flex; align-items:center; gap:8px; padding:6px 14px;
         background:var(--panel); border-bottom:1px solid var(--border); flex-shrink:0; }
  .nav .tl  { font-family:'Syne',sans-serif; font-weight:800; font-size:18px; color:#fff; }
  .nav .dl  { font-size:10px; color:var(--muted); }
  .nav .pos { margin-left:auto; font-size:10px; color:var(--muted); }
  .btn { background:var(--border); border:1px solid var(--muted); color:var(--text);
         font-family:inherit; font-size:10px; padding:4px 12px; border-radius:3px;
         cursor:pointer; transition:all .15s; letter-spacing:.04em; }
  .btn:hover { background:var(--accent); border-color:var(--accent); color:#000; }
  .btn:disabled { opacity:.3; cursor:default; }

  .frame-wrap { flex:1; overflow:hidden; position:relative; }
  iframe { width:100%; height:100%; border:none; background:var(--bg); }

  .fallback { display:flex; align-items:center; justify-content:center;
              width:100%; height:100%; }
  .fallback img { max-width:100%; max-height:100%; object-fit:contain; border-radius:4px; }

  .empty { text-align:center; color:var(--muted); font-size:12px; }
  .empty span { display:block; font-size:28px; margin-bottom:10px; opacity:.3; }

  .legend { display:flex; gap:14px; padding:5px 14px; flex-shrink:0;
            background:var(--panel); border-top:1px solid var(--border);
            font-size:9.5px; color:var(--muted); }
  .ldot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px; }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">⬡ SWING VIEWER</div>
    <div class="sep"></div>
    <div class="hinfo">SET Pivot Breakout · Click a signal dot to analyse</div>
    <input id="search" placeholder="Filter ticker…" oninput="filterList(this.value)">
    <div class="hcount" id="hcount"></div>
  </header>

  <div class="sidebar" id="sidebar"></div>

  <div class="main">
    <div class="nav">
      <button class="btn" id="btn-prev" onclick="navigate(-1)">← PREV</button>
      <button class="btn" id="btn-next" onclick="navigate(+1)">NEXT →</button>
      <div style="width:10px"></div>
      <div class="tl" id="nav-ticker">—</div>
      <div class="dl" id="nav-date"></div>
      <div class="pos" id="nav-pos"></div>
    </div>

    <div class="frame-wrap" id="frame-wrap">
      <div class="empty"><span>📊</span>Select a chart from the list<br><br>
        <span style="font-size:11px;opacity:.5">Green dots = all filters pass<br>
        Yellow = RSM fail · Blue = RVol fail · Grey = below SMA50</span></div>
    </div>

    <div class="legend">
      <span><span class="ldot" style="background:#ff6ec7"></span>Entry — all filters pass (traded, matches PNG)</span>
      <span><span class="ldot" style="background:#2196F3"></span>High RVol, RSM below threshold</span>
      <span><span class="ldot" style="background:#26a69a"></span>Normal volume</span>
      <span><span class="ldot" style="background:#ffd740"></span>RSM below threshold</span>
      <span><span class="ldot" style="background:#888"></span>Below SMA50</span>
    </div>
  </div>
</div>

<script>
const charts = CHARTS_JSON;
let current = -1;
let filtered = charts.map((_,i) => i);

function buildList() {
  const sb = document.getElementById('sidebar');
  charts.forEach((c,i) => {
    const el = document.createElement('div');
    el.className = 'item'; el.id = 'item-'+i;
    const badge = c.interactive ? '<span class="ibadge">interactive</span>' : '';
    el.innerHTML = `<div class="idx">${i+1}</div>
      <div class="iinfo">
        <div class="iticker">${c.ticker.replace(/_/g,'.')}${badge}</div>
        <div class="idate">${c.date}</div>
      </div>`;
    el.onclick = () => select(i);
    sb.appendChild(el);
  });
  updateCount();
}

function filterList(q) {
  q = q.toLowerCase(); filtered = [];
  charts.forEach((c,i) => {
    const el = document.getElementById('item-'+i);
    const match = c.ticker.toLowerCase().includes(q) || c.date.includes(q);
    el.classList.toggle('hidden', !match);
    if (match) filtered.push(i);
  });
  updateCount();
}

function updateCount() {
  document.getElementById('hcount').textContent = filtered.length + ' charts';
}

function select(i) {
  if (current >= 0) document.getElementById('item-'+current)?.classList.remove('active');
  current = i;
  document.getElementById('item-'+i)?.classList.add('active');
  document.getElementById('item-'+i)?.scrollIntoView({block:'nearest'});
  const c = charts[i];
  document.getElementById('nav-ticker').textContent = c.ticker.replace(/_/g,'.');
  document.getElementById('nav-date').textContent   = c.date;
  document.getElementById('nav-pos').textContent    =
    (filtered.indexOf(i)+1) + ' / ' + filtered.length;
  document.getElementById('btn-prev').disabled = filtered.indexOf(i) <= 0;
  document.getElementById('btn-next').disabled = filtered.indexOf(i) >= filtered.length-1;

  const wrap = document.getElementById('frame-wrap');
  if (c.interactive && c.html_file) {
    wrap.innerHTML = `<iframe src="/chart/${c.html_file}" allowfullscreen></iframe>`;
  } else if (c.png_file) {
    wrap.innerHTML = `<div class="fallback"><img src="/chart/${c.png_file}"></div>`;
  } else {
    wrap.innerHTML = `<div class="empty"><span>⚠️</span>Chart file missing</div>`;
  }
}

function navigate(dir) {
  const fi = filtered.indexOf(current);
  const ni = fi + dir;
  if (ni >= 0 && ni < filtered.length) select(filtered[ni]);
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key==='ArrowRight'||e.key==='ArrowDown') { e.preventDefault(); navigate(+1); }
  if (e.key==='ArrowLeft' ||e.key==='ArrowUp')   { e.preventDefault(); navigate(-1); }
});

buildList();
if (charts.length > 0) select(0);
else document.getElementById('frame-wrap').innerHTML =
  '<div class="empty"><span>📊</span>No charts yet — run <code>python main.py TICKER.BK</code> first, then refresh.</div>';
</script>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            charts = get_charts()
            html   = SHELL.replace('CHARTS_JSON', json.dumps(charts))
            self._send(200, 'text/html; charset=utf-8', html.encode())

        elif path.startswith('/chart/'):
            fname = path[7:]
            fpath = CHARTS_DIR / fname
            if not fpath.exists():
                self._send(404, 'text/plain', b'Not found')
                return
            ctype = 'text/html; charset=utf-8' if fpath.suffix == '.html' else 'image/png'
            mode  = 'r' if fpath.suffix == '.html' else 'rb'
            with open(fpath, mode) as f:
                data = f.read()
            if isinstance(data, str):
                data = data.encode()
            self._send(200, ctype, data)

        else:
            self._send(404, 'text/plain', b'Not found')

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    html_n = len(list(CHARTS_DIR.glob('*.html')))
    png_n  = len(list(CHARTS_DIR.glob('*.png')))
    print(f'╔══════════════════════════════════════╗')
    print(f'║  Swing Trader · Chart Viewer         ║')
    print(f'╠══════════════════════════════════════╣')
    print(f'║  Interactive charts : {html_n:<18}║')
    print(f'║  PNG charts         : {png_n:<18}║')
    print(f'║  URL  : http://localhost:{PORT}        ║')
    print(f'║  Stop : Ctrl+C                       ║')
    print(f'╚══════════════════════════════════════╝')
    if html_n == 0 and png_n == 0:
        print('  (No charts yet — run main.py to generate them, then refresh)')
    ThreadingHTTPServer(('localhost', PORT), Handler).serve_forever()