"""
chart_combined.py — slim single-ticker standalone chart for `python main.py --view`.

  generate_view_html(chart_data, charts_dir, fname='chart.html') -> path

Replaces the old multi-MB all-stocks generator. Emits a tiny self-contained HTML
that loads lightweight-charts + the shared frontend/static/lwc-render.js renderer
and inlines ONE stock's get_chart_data() dict. The web app no longer uses this —
charts there render natively via /api/chart/{ticker}; this is a local debug tool.
"""

import os
import json

_RENDER_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'frontend', 'static', 'lwc-render.js',
)


def generate_view_html(chart_data: dict, charts_dir: str, fname: str = 'chart.html') -> str:
    if not chart_data:
        return None

    try:
        with open(_RENDER_JS, encoding='utf-8') as f:
            render_js = f.read()
    except OSError:
        render_js = ''

    ticker = str(chart_data.get('ticker', '')).replace('.BK', '').replace('.AX', '')
    data_json = json.dumps(chart_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Breakout Signal — {ticker}</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  html,body{{height:100%;font-family:ui-sans-serif,system-ui,sans-serif;}}
  .bar{{height:36px;display:flex;align-items:center;gap:14px;padding:0 14px;
        border-bottom:1px solid #e5e7eb;font-size:13px;}}
  .tk{{font-weight:700;color:#111827;}}
  .leg{{margin-left:auto;display:flex;gap:12px;font-size:10px;color:#6b7280;}}
  #chart{{position:absolute;top:36px;left:0;right:0;bottom:0;}}
</style>
</head>
<body>
<div class="bar">
  <span class="tk">{ticker}</span>
  <span style="color:#6b7280">฿{chart_data.get('last_close', '—')}</span>
  <span class="leg">
    <span style="color:#6366f1">EMA10</span>
    <span style="color:#f59e0b">EMA20</span>
    <span style="color:#ef4444">SMA50</span>
  </span>
</div>
<div id="chart"></div>
<script>{render_js}</script>
<script>
  const D = {data_json};
  window.renderLwcChart(document.getElementById('chart'), D);
</script>
</body>
</html>"""

    os.makedirs(charts_dir, exist_ok=True)
    path = os.path.join(charts_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path
