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
    filename:    str  = None,
    portfolio:   dict = None,
    tv_prefix:   str  = 'SET',
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

    # Build backtest summary data for the BACKTEST tab
    # Build ticker → sidebar index map
    ticker_to_idx = {d['ticker']: i for i, d in enumerate(stocks_data)}

    FILTER_TYPES = ['Prime', 'STR', 'RVOL', 'RSM', 'SMA50']

    bt_rows = []
    for r in results:
        all_r_trades = r.get('trades', [])
        prime_trades = [t for t in all_r_trades if t.get('filter_type') == 'Prime']
        wins   = [t for t in prime_trades if t.get('win')]
        losses = [t for t in prime_trades if not t.get('win')]
        atr_pcts = [t.get('stretch', 0) for t in prime_trades if t.get('stretch', 0) > 0]
        # Per-type breakdown for filter
        by_type = {}
        for ft in FILTER_TYPES:
            ts = [t for t in all_r_trades if t.get('filter_type') == ft]
            if ts:
                tw = [t for t in ts if t.get('win')]
                tl = [t for t in ts if not t.get('win')]
                by_type[ft] = dict(
                    n=len(ts),
                    wr=round(len(tw)/len(ts)*100,1) if ts else 0,
                    avg_win=round(sum(t.get('ret_pct',0) for t in tw)/len(tw),2) if tw else None,
                    avg_loss=round(sum(t.get('ret_pct',0) for t in tl)/len(tl),2) if tl else None,
                    # pnl_capital: sum of (trade_profit / starting_capital) — same units as total_pnl_pct
                    pnl_capital=round(sum(t.get('pnl_pct',0) for t in ts), 2),
                    avg_stretch=round(sum(t.get('stretch',0) for t in ts if t.get('stretch',0)>0)/
                                      max(1,sum(1 for t in ts if t.get('stretch',0)>0)),2)
                              if any(t.get('stretch',0)>0 for t in ts) else None,
                )
        bt_rows.append(dict(
            ticker      = r['ticker'].replace('.BK',''),
            ticker_full = r['ticker'],
            idx         = ticker_to_idx.get(r['ticker'], -1),
            rsm         = round(r.get('rs_momentum', 0), 0),
            trades      = len(prime_trades),
            wr          = round(len(wins) / len(prime_trades) * 100, 1) if prime_trades else 0,
            pnl_pct     = round(r.get('total_pnl_pct', 0), 2),
            avg_win     = round(sum(t.get('ret_pct',0) for t in wins)   / len(wins),   2) if wins   else None,
            avg_loss    = round(sum(t.get('ret_pct',0) for t in losses) / len(losses), 2) if losses else None,
            avg_stretch = round(sum(atr_pcts) / len(atr_pcts), 2) if atr_pcts else None,
            has_signal  = bool(r.get('today_signal')),
            has_pending = bool(r.get('pending')),
            by_type     = by_type,
        ))
    # Overall summary — Prime only (default)
    all_trades  = [t for r in results for t in r.get('trades', []) if t.get('filter_type') == 'Prime']
    all_wins    = [t for t in all_trades if t.get('win')]
    overall_wr  = round(len(all_wins) / len(all_trades) * 100, 1) if all_trades else 0
    overall_pnl = round(sum(r.get('total_pnl_pct', 0) for r in results), 2)
    avg_ret_win  = round(sum(t.get('ret_pct',0) for t in all_wins) / len(all_wins), 2) if all_wins else 0
    all_losses   = [t for t in all_trades if not t.get('win')]
    avg_ret_loss = round(sum(t.get('ret_pct',0) for t in all_losses) / len(all_losses), 2) if all_losses else 0

    backtest_json = json.dumps(dict(
        rows      = sorted(bt_rows, key=lambda x: x['pnl_pct'], reverse=True),
        n_trades  = len(all_trades),
        wr        = overall_wr,
        pnl_pct   = overall_pnl,
        avg_win   = avg_ret_win,
        avg_loss  = avg_ret_loss,
        n_stocks  = len(results),
    ))

    # ── Watchlist tab data: only pending stocks grouped by MA position ────
    wl_groups = {'> MA10': [], '> MA20': [], '> MA50': []}
    for r in sorted(results, key=lambda x: x['ticker']):
        if not r.get('pending'):
            continue
        suffix = '.BK' if tv_prefix == 'SET' else '.AX'
        t  = r['ticker'].replace(suffix, '')
        tv = f'{tv_prefix}:{t}'
        if r.get('above_ema10'):
            wl_groups['> MA10'].append(tv)
        elif r.get('above_ema20'):
            wl_groups['> MA20'].append(tv)
        else:
            wl_groups['> MA50'].append(tv)

    # Build copy-paste string: ###> MA10,SET:X,SET:Y,###> MA20,...
    wl_parts = []
    for label, tickers in wl_groups.items():
        if tickers:
            wl_parts.append('###' + label)
            wl_parts.extend(tickers)
    watchlist_copystr = ','.join(wl_parts)

    watchlist_json = json.dumps(dict(
        groups   = wl_groups,
        copy_str = watchlist_copystr,
        date     = date_str,
    ))

    # ── Sector rotation data ──────────────────────────────────────────────────
    from collections import defaultdict as _dd
    _chart_map = {d['ticker']: d for d in stocks_data}
    _sec = _dd(lambda: dict(rsm_sum=0.0, rsm_count=0, breakouts=0, stock_list=[]))
    for r in results:
        sec_name = (r.get('sector') or 'Unknown').strip() or 'Unknown'
        s        = _sec[sec_name]
        rsm      = r.get('rs_momentum', 0) or 0
        if rsm > 0:
            s['rsm_sum'] += rsm; s['rsm_count'] += 1
        cd      = _chart_map.get(r['ticker'], {})
        rvol    = round(float(cd.get('rvol_now', 0) or 0), 2)
        sig     = r.get('today_signal')
        stretch = round(float((sig or {}).get('stretch', 0) or 0), 2)
        s['stock_list'].append(dict(
            ticker     = r['ticker'].replace('.BK', '').replace('.AX', ''),
            rsm        = round(rsm, 1),
            rvol       = rvol,
            stretch    = stretch,
            has_signal = bool(sig),
            has_pending= bool(r.get('pending')),
        ))
        if sig: s['breakouts'] += 1
    _sec_rows = []
    for name, s in _sec.items():
        avg = round(s['rsm_sum'] / s['rsm_count'], 1) if s['rsm_count'] else 0
        sl  = sorted(s['stock_list'], key=lambda x: (not x['has_signal'], not x['has_pending'], -x['rsm']))
        _sec_rows.append(dict(
            name=name, stocks=len(s['stock_list']),
            avg_rsm=avg, breakouts=s['breakouts'], stock_list=sl,
        ))
    _sec_rows.sort(key=lambda x: x['avg_rsm'], reverse=True)
    sector_json = json.dumps(_sec_rows)

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
        pnl_col  = '#16a34a' if pnl_pct >= 0 else '#dc2626'
        pnl_str  = f'{pnl_pct:+.1f}%' if trades else '—'
        rvol_str = f'{rvol:.1f}x' if rvol else '—'
        rvol_col = '#16a34a' if rvol >= rvol_min else '#9ca3af'
        # section: 'sig' | 'wtc' | ''
        item_cls = f'sb-item sb-{section}' if section else 'sb-item'
        # For signal stocks show criteria type; others show RSM value
        _CRIT_COL = {'Prime':'#ff6ec7','RVOL':'#3b82f6','STR':'#ef4444','RSM':'#f97316','SMA50':'#f59e0b'}
        if section == 'sig':
            sigs = d.get('signals', [])
            latest_ft = sigs[-1].get('filter_type', '') if sigs else ''
            rsm_label = latest_ft or 'Prime'
            rsm_color = _CRIT_COL.get(rsm_label, '#ff6ec7')
        else:
            rsm_label = f'RSM {rsm:.0f}'
            rsm_color = '#f59e0b' if rsm >= 80 else '#9ca3af'
        # For signal stocks add inline border-left-color matching criteria
        border_style = f' style="border-left-color:{rsm_color}"' if section == 'sig' else ''
        return f"""
        <div class="{item_cls}" id="sb-{idx}" onclick="loadStock({idx})"{border_style}>
          <div class="sb-top">
            <span class="sb-ticker">{d['ticker'].replace('.BK','')}</span>
            <span class="sb-rsm" style="color:{rsm_color}">{rsm_label}</span>
          </div>
          <div class="sb-bot">
            <span class="sb-rvol" style="color:{rvol_col}">RVol {rvol_str}</span>
            <span class="sb-pnl" style="color:{pnl_col}">{pnl_str}</span>
          </div>
        </div>"""

    sidebar_parts = []

    # ── Section 0: INTRADAY placeholder (populated at runtime via fetch) ──
    sidebar_parts.append('<div id="intra-section"></div>')

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
            f'<div class="sb-section-hdr">ALL STOCKS ({len(rest_stocks)})</div>')
        for i, d in enumerate(rest_stocks, n_sig + n_wtc):
            sidebar_parts.append(_sb_item(i, d, ''))

    sidebar_html = '\n'.join(sidebar_parts)

    portfolio_json = json.dumps(portfolio) if portfolio else 'null'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Breakout Signal — Chart [{date_str.replace('_','-')}]</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  html,body{{height:100%;overflow:hidden;font-family:ui-sans-serif,system-ui,sans-serif;font-size:13px;}}
  /* ── Layout ── */
  .app{{display:grid;grid-template-columns:200px 1fr 280px;grid-template-rows:1fr;height:100vh;}}
  /* ── Sidebar ── */
  .sidebar{{display:flex;flex-direction:column;overflow:hidden;background:#fff;border-right:1px solid #e5e7eb;}}
  .sb-head{{padding:10px;border-bottom:1px solid #e5e7eb;flex-shrink:0;}}
  .sb-stats{{font-size:11px;color:#6b7280;margin-bottom:6px;}}
  .sb-search{{width:100%;border:1px solid #e5e7eb;border-radius:6px;padding:5px 8px;font-size:12px;
              outline:none;color:#111827;}}
  .sb-search:focus{{border-color:#6366f1;}}
  .sb-list{{flex:1;overflow-y:auto;}}
  .sb-list::-webkit-scrollbar{{width:3px;}}
  .sb-list::-webkit-scrollbar-thumb{{background:#e5e7eb;border-radius:2px;}}
  .sb-section-hdr{{padding:6px 10px;font-size:10px;font-weight:700;letter-spacing:.08em;
                   text-transform:uppercase;border-bottom:1px solid #f3f4f6;
                   background:#f9fafb;color:#6b7280;}}
  .sb-hdr-sig{{color:#db2777;background:#fdf2f8;border-left:3px solid #db2777;}}
  .sb-hdr-wtc{{color:#d97706;background:#fffbeb;border-left:3px solid #d97706;}}
  .sb-hdr-intra{{color:#6366f1;background:#eef2ff;border-left:3px solid #6366f1;}}
  .sb-intra{{border-left-color:rgba(99,102,241,.3);background:#f8f8ff;}}
  .sb-intra.active{{border-left-color:#6366f1;background:#eef2ff;}}
  .sb-item{{padding:7px 10px 7px 12px;cursor:pointer;border-bottom:1px solid #f3f4f6;
            transition:background .1s;border-left:3px solid transparent;}}
  .sb-item:hover{{background:#f5f3ff;}}
  .sb-item.active{{background:#eef2ff;border-left-color:#6366f1;}}
  .sb-sig{{border-left-color:rgba(219,39,119,.3);background:#fff5fb;}}
  .sb-sig.active{{border-left-color:#db2777;background:#fde8f4;}}
  .sb-wtc{{border-left-color:rgba(217,119,6,.3);background:#fffdf5;}}
  .sb-wtc.active{{border-left-color:#d97706;background:#fef3c7;}}
  .sb-top{{display:flex;justify-content:space-between;align-items:baseline;}}
  .sb-bot{{display:flex;justify-content:space-between;margin-top:3px;}}
  .sb-ticker{{font-weight:700;font-size:13px;color:#111827;}}
  .sb-rsm{{font-size:10px;color:#d97706;}}
  .sb-rvol,.sb-pnl{{font-size:10px;}}
  /* ── Chart area ── */
  .chart-area{{position:relative;background:#f9fafb;overflow:hidden;}}
  #chart-container{{width:100%;height:100%;}}
  #no-stock{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
             color:#9ca3af;font-size:14px;pointer-events:none;}}
  /* ── Signal panel ── */
  .panel{{background:#fff;border-left:1px solid #e5e7eb;display:flex;flex-direction:column;overflow:hidden;}}
  .panel::-webkit-scrollbar{{width:3px;}}
  .sig-header{{padding:10px 14px 8px;border-bottom:1px solid #e5e7eb;font-size:11px;
               color:#6b7280;letter-spacing:.05em;flex-shrink:0;}}
  .sig-list{{flex:1;overflow-y:auto;}}
  .sig-list::-webkit-scrollbar{{width:3px;}}
  .sig-list::-webkit-scrollbar-thumb{{background:#e5e7eb;border-radius:2px;}}
  .sig-item{{padding:8px 12px;cursor:pointer;border-bottom:1px solid #f3f4f6;
             transition:background .1s;display:flex;align-items:center;gap:8px;}}
  .sig-item:hover{{background:#f5f3ff;}}
  .sig-item.active{{background:#eef2ff;border-left:2px solid #6366f1;padding-left:10px;}}
  .sig-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}
  .sig-info{{flex:1;min-width:0;}}
  .sig-date{{font-size:12px;color:#111827;font-weight:500;}}
  .sig-sub{{font-size:11px;color:#6b7280;margin-top:1px;}}
  .analysis{{border-top:1px solid #e5e7eb;padding:12px 14px;flex-shrink:0;}}
  .an-title{{font-weight:700;font-size:13px;color:#6366f1;margin-bottom:8px;letter-spacing:.03em;}}
  .an-row{{display:flex;justify-content:space-between;align-items:center;
           padding:4px 0;border-bottom:1px solid #f3f4f6;font-size:12px;}}
  .an-row:last-child{{border-bottom:none;}}
  .an-label{{color:#6b7280;}}
  .an-value{{color:#111827;font-weight:500;text-align:right;}}
  .an-value.green{{color:#16a34a;}} .an-value.red{{color:#dc2626;}}
  .an-value.yellow{{color:#d97706;}} .an-value.blue{{color:#2563eb;}}
  .an-value.grey{{color:#9ca3af;}}
  .an-sep{{height:1px;background:#f3f4f6;margin:6px 0;}}
  .an-empty{{color:#9ca3af;font-size:12px;text-align:center;padding:16px 0;}}
  .filter-row{{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px;}}
  .badge{{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;letter-spacing:.03em;border:1px solid;}}
  .badge.pass{{background:#f0fdf4;color:#16a34a;border-color:#bbf7d0;}}
  .badge.fail{{background:#fef2f2;color:#dc2626;border-color:#fecaca;}}
  .trade-summary{{border-top:1px solid #e5e7eb;flex-shrink:0;}}
  .ts-title{{color:#6b7280;font-size:10px;letter-spacing:.05em;text-transform:uppercase;
             padding:8px 12px 4px;}}
  .ts-row{{display:flex;justify-content:space-between;align-items:center;
           padding:5px 12px;border-bottom:1px solid #f3f4f6;font-size:11px;}}
  .ts-row:last-child{{border-bottom:none;}}
  /* ── Filter badges ── */
  .tr-filter{{font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700;}}
  .tf-prime{{background:#fdf4ff;color:#a21caf;}}
  .tf-rvol{{background:#eff6ff;color:#1d4ed8;}}
  .tf-rsm{{background:#f0fdf4;color:#15803d;}}
  .tf-sma50{{background:#fffbeb;color:#b45309;}}
  .tf-str{{background:#fef2f2;color:#b91c1c;}}
  /* ── LWC chart legend overlay ── */
  .chart-legend{{position:absolute;top:6px;left:10px;z-index:10;display:flex;gap:10px;
                 pointer-events:none;flex-wrap:wrap;background:rgba(255,255,255,.85);
                 padding:4px 8px;border-radius:6px;font-size:10px;color:#6b7280;}}
  .leg-item{{display:flex;align-items:center;gap:4px;}}
  .leg-swatch{{width:16px;height:2px;border-radius:1px;}}
</style>
</head>
<body class="bg-gray-50 text-gray-800">

<div class="app">

  <!-- ── Sidebar ── -->
  <div class="sidebar">
    <div class="sb-head">
      <div class="sb-stats">
        <span class="text-gray-800">{total}</span> stocks &nbsp;·&nbsp;
        <span class="text-pink-600">{n_sig}</span> signals &nbsp;·&nbsp;
        <span class="text-amber-500">{n_wtc}</span> watching
      </div>
      <input class="sb-search" id="sb-search" type="text"
             placeholder="Search ticker…" oninput="filterSidebar(this.value)">
    </div>
    <div class="sb-list" id="sb-list">
      {sidebar_html}
    </div>
  </div>

  <!-- ── Chart ── -->
  <div class="chart-area" id="chart-area">
    <div id="chart-container"></div>
    <!-- legend overlay -->
    <div class="chart-legend" id="chart-legend" style="display:none">
      <div class="leg-item"><div class="leg-swatch" style="background:#6366f1"></div>EMA10</div>
      <div class="leg-item"><div class="leg-swatch" style="background:#f59e0b;height:1px"></div>EMA20</div>
      <div class="leg-item"><div class="leg-swatch" style="background:#ef4444"></div>SMA50</div>
      <div class="leg-item"><div class="leg-swatch" style="background:#9ca3af;height:1px"></div>SMA200</div>

    </div>
    <div id="no-stock">← Select a stock from the sidebar</div>
  </div>

  <!-- ── Signal panel ── -->
  <div class="panel">
    <div class="sig-header">
      SIGNALS — <span id="sig-count" class="text-gray-800 font-medium">—</span>
      <span id="sig-filter-info" style="font-size:10px;display:block;margin-top:2px"></span>
    </div>
    <div class="sig-list" id="sig-list"></div>
    <div class="analysis" id="analysis">
      <div class="an-empty">← Click a signal to analyse</div>
    </div>
    <div class="trade-summary" id="trade-summary"></div>
  </div>
</div>

<script>
// ── Data ──────────────────────────────────────────────────────────────────────
const ALL_STOCKS = {all_stocks_json};
const BT         = {backtest_json};
const PT         = {portfolio_json};
const WL         = {watchlist_json};
const SECTOR     = {sector_json};
const TV_PREFIX  = '{tv_prefix}';
const TICKER_SUFFIX = TV_PREFIX === 'SET' ? '.BK' : '.AX';
let D = null;
let currentStockIdx = null;
let selectedSigIdx  = null;

// ── LWC state ────────────────────────────────────────────────────────────────
let _chart = null;
let _candle = null;
let _activeLines = [];

function _destroyChart() {{
  if (_chart) {{ try {{ _chart.remove(); }} catch(e) {{}} _chart = null; _candle = null; }}
  _activeLines = [];
}}

// ── Load stock ────────────────────────────────────────────────────────────────
function loadStock(idx) {{
  if (currentStockIdx != null)
    document.getElementById('sb-'+currentStockIdx)?.classList.remove('active');
  currentStockIdx = idx;
  D = ALL_STOCKS[idx];
  document.getElementById('sb-'+idx)?.classList.add('active');
  document.getElementById('sb-'+idx)?.scrollIntoView({{block:'nearest'}});
  document.getElementById('no-stock').style.display = 'none';
  document.getElementById('chart-legend').style.display = '';
  selectedSigIdx = null;
  document.getElementById('trade-summary').innerHTML = '';
  document.getElementById('analysis').innerHTML = '<div class="an-empty">← Click a signal to analyse</div>';
  renderChart(D);
  buildSignalList();
}}

// ── Render chart with LWC ─────────────────────────────────────────────────────
function renderChart(D) {{
  _destroyChart();
  const container = document.getElementById('chart-container');
  container.innerHTML = '';

  _chart = LightweightCharts.createChart(container, {{
    autoSize: true,
    layout: {{
      background: {{ color: '#ffffff' }},
      textColor:  '#374151',
      fontSize:   11,
    }},
    grid: {{
      vertLines: {{ color: '#f3f4f6' }},
      horzLines: {{ color: '#f3f4f6' }},
    }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    rightPriceScale: {{ borderColor: '#e5e7eb' }},
    timeScale: {{
      borderColor: '#e5e7eb',
      rightOffset: 5,
      fixLeftEdge: false,
    }},
  }});

  // ── Constrain main price scale to top 72% ──
  _chart.priceScale('right').applyOptions({{
    scaleMargins: {{ top: 0.04, bottom: 0.28 }},
  }});

  // ── Candlestick ──
  _candle = _chart.addCandlestickSeries({{
    upColor:       '#26a69a',
    downColor:     '#ef5350',
    borderVisible: false,
    wickUpColor:   '#26a69a',
    wickDownColor: '#ef5350',
  }});
  _candle.setData(D.candles.map(c => ({{
    time: c.d, open: c.o, high: c.h, low: c.l, close: c.c,
  }})));

  // ── Volume (RVOL) histogram — bottom 15% ──
  const volS = _chart.addHistogramSeries({{
    priceScaleId:       'rvol',
    lastValueVisible:   false,
    priceLineVisible:   false,
  }});
  _chart.priceScale('rvol').applyOptions({{
    scaleMargins: {{ top: 0.86, bottom: 0 }},
    visible: false,
  }});
  volS.setData(D.candles.map(c => ({{
    time:  c.d,
    value: c.rv,
    color: c.rv >= D.rvol_min ? 'rgba(22,163,74,0.45)' : 'rgba(209,213,219,0.5)',
  }})));

  // RVOL threshold line
  const rvolThresh = _chart.addLineSeries({{
    priceScaleId:          'rvol',
    color:                 'rgba(217,119,6,0.55)',
    lineWidth:             1,
    lineStyle:             LightweightCharts.LineStyle.Dashed,
    lastValueVisible:      false,
    priceLineVisible:      false,
    crosshairMarkerVisible: false,
  }});
  rvolThresh.setData([
    {{ time: D.candles[0].d,                         value: D.rvol_min }},
    {{ time: D.candles[D.candles.length - 1].d,      value: D.rvol_min }},
  ]);

  // ── RSM background highlights (vertical grey bands for below-threshold bars) ──
  const rsmBgS = _chart.addHistogramSeries({{
    priceScaleId:    'rsm_bg',
    color:           'rgba(209,213,219,0.3)',
    lastValueVisible: false,
    priceLineVisible: false,
  }});
  _chart.priceScale('rsm_bg').applyOptions({{
    scaleMargins: {{ top: 0, bottom: 0 }},
    visible: false,
  }});
  rsmBgS.setData(D.candles.map((c, i) => {{
    const below = D.rsm && D.rsm[i] != null && D.rsm[i] < D.rsm_min;
    return {{ time: c.d, value: below ? 1 : 0, color: below ? 'rgba(209,213,219,0.3)' : 'rgba(0,0,0,0)' }};
  }}));

  // ── Moving averages ──
  const maList = [
    {{ key:'ema10',  color:'#6366f1', width:1.5, style: LightweightCharts.LineStyle.Solid  }},
    {{ key:'ema20',  color:'#f59e0b', width:1,   style: LightweightCharts.LineStyle.Dashed }},
    {{ key:'sma50',  color:'#ef4444', width:1.8, style: LightweightCharts.LineStyle.Solid  }},
    {{ key:'sma200', color:'#9ca3af', width:0.9, style: LightweightCharts.LineStyle.Dashed }},
  ];
  maList.forEach(({{ key, color, width, style }}) => {{
    if (!D[key]) return;
    const ms = _chart.addLineSeries({{
      color, lineWidth: width, lineStyle: style,
      lastValueVisible: false, priceLineVisible: false,
    }});
    const pts = [];
    D.candles.forEach((c, i) => {{
      const v = D[key][i];
      if (v != null) pts.push({{ time: c.d, value: v }});
    }});
    if (pts.length) ms.setData(pts);
  }});

  // ── Helper: bar index → date string ──
  const barDate = i => D.candles[Math.max(0, Math.min(D.candles.length - 1, i))].d;

  // ── Segmented line helper (hz and trendlines) ──
  const addSegLine = (seg, color, width, style) => {{
    if (!seg.xs || seg.xs.length < 2) return;
    const s = _chart.addLineSeries({{
      color, lineWidth: width,
      lineStyle: style ?? LightweightCharts.LineStyle.Solid,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    }});
    const dateMap = new Map();
    seg.xs.forEach((x, i) => dateMap.set(barDate(x), seg.ys[i]));
    const pts = [...dateMap.entries()].map(([time, value]) => ({{ time, value }}));
    pts.sort((a, b) => a.time < b.time ? -1 : 1);
    if (pts.length >= 2) s.setData(pts);
  }};

  // ── Horizontal resistance lines (segmented) ──
  (D.hz_fast || []).forEach(seg => addSegLine(seg, 'rgba(249,115,22,0.7)',  1, LightweightCharts.LineStyle.Dashed));
  (D.hz_slow || []).forEach(seg => addSegLine(seg, 'rgba(253,186,116,0.7)', 1, LightweightCharts.LineStyle.Dashed));

  // ── Trendlines ──
  (D.tl_fast || []).forEach(seg => addSegLine(seg, 'rgba(249,115,22,0.75)',  1.5, LightweightCharts.LineStyle.Solid));
  (D.tl_slow || []).forEach(seg => addSegLine(seg, 'rgba(253,186,116,0.75)', 1.5, LightweightCharts.LineStyle.Solid));

  // ── Signal + trade markers ──
  const CRIT_COLOR = {{
    Prime: '#ff6ec7', RVOL: '#3b82f6', STR: '#ef4444', RSM: '#f97316', SMA50: '#f59e0b',
  }};
  const markers = [];
  (D.signals || []).forEach(s => {{
    const col = CRIT_COLOR[s.filter_type] || s.col || '#ff6ec7';
    markers.push({{
      time:     s.date,
      position: 'belowBar',
      color:    col,
      shape:    'arrowUp',
      text:     (s.filter_type && s.filter_type !== 'Below') ? s.filter_type : '',
      size:     1,
    }});
  }});
  (D.trades || []).forEach(t => {{
    const exitColor = t.exit_reason === 'SL'    ? '#dc2626'
                    : t.exit_reason === 'BE'    ? '#f97316'
                    : t.exit_reason === 'EMA10' ? '#f59e0b'
                    : '#6b7280';
    if (t.tp1_hit && t.tp1_bar != null && D.candles[t.tp1_bar])
      markers.push({{ time: D.candles[t.tp1_bar].d, position:'aboveBar', color:'#16a34a', shape:'arrowDown', text:'TP1', size:0.7 }});
    if (t.tp2_hit && t.tp2_bar != null && D.candles[t.tp2_bar])
      markers.push({{ time: D.candles[t.tp2_bar].d, position:'aboveBar', color:'#15803d', shape:'arrowDown', text:'TP2', size:0.7 }});
    if (t.exit_bar != null && D.candles[t.exit_bar] && t.exit_reason !== 'End')
      markers.push({{ time: D.candles[t.exit_bar].d, position:'aboveBar', color:exitColor,
                      shape:'arrowDown', text: t.exit_reason==='EMA10'?'MA10':t.exit_reason, size:0.7 }});
  }});
  markers.sort((a,b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
  _candle.setMarkers(markers);

  // Set visible range to last 1 year (≈252 trading days)
  (function() {{
    const candles = D.candles;
    const lastD   = candles[candles.length - 1].d;
    const fromDt  = new Date(lastD);
    fromDt.setFullYear(fromDt.getFullYear() - 1);
    const fromD   = fromDt.toISOString().slice(0, 10);
    try {{
      _chart.timeScale().setVisibleRange({{ from: fromD, to: lastD }});
    }} catch(e) {{
      _chart.timeScale().fitContent();
    }}
  }})();

  // Resize observer — just fitContent on resize (autoSize handles dimensions)
  const ro = new ResizeObserver(() => {{
    if (_chart) _chart.timeScale().fitContent();
  }});
  ro.observe(container);

  // Click on chart → find nearest signal
  _chart.subscribeClick(param => {{
    if (!param.time || !D) return;
    const targetDate = param.time;
    let best = null, bestDiff = Infinity;
    D.signals.forEach((s, i) => {{
      const diff = Math.abs(new Date(s.date) - new Date(targetDate));
      if (diff < bestDiff && diff < 5 * 86400000) {{ bestDiff = diff; best = i; }}
    }});
    if (best != null) selectSignal(best);
  }});
}}

// ── Sidebar search / filter ───────────────────────────────────────────────────
function filterSidebar(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.sb-item').forEach(el => {{
    const t = el.querySelector('.sb-ticker')?.textContent.toLowerCase() || '';
    el.style.display = t.includes(q) ? '' : 'none';
  }});
}}

// ── Keyboard navigation ───────────────────────────────────────────────────────
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{
    document.getElementById('sb-search').value = '';
    filterSidebar('');
    return;
  }}
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
    e.preventDefault();
    const vis = [...document.querySelectorAll('.sb-item')]
      .filter(el => el.style.display !== 'none')
      .map(el => parseInt(el.id.replace('sb-', '')));
    if (!vis.length) return;
    const pos  = vis.indexOf(currentStockIdx);
    const next = e.key === 'ArrowDown' ? vis[Math.min(pos+1, vis.length-1)] : vis[Math.max(pos-1,0)];
    if (next !== currentStockIdx) loadStock(next);
  }}
}});

// ── Select a signal ───────────────────────────────────────────────────────────
function selectSignal(idx) {{
  // Remove previous overlay price lines
  _activeLines.forEach(pl => {{ try {{ _candle?.removePriceLine(pl); }} catch(e) {{}} }});
  _activeLines = [];
  document.querySelectorAll('.sig-item.active').forEach(el => el.classList.remove('active'));
  if (idx == null || !D) return;
  selectedSigIdx = idx;
  const el = document.getElementById('sig-' + idx);
  el?.classList.add('active');
  el?.scrollIntoView({{ block: 'nearest' }});

  const s = D.signals[idx];
  if (_chart && _candle && s) {{
    // Scroll to show the signal with context
    const barIdx = s.i;
    const from   = D.candles[Math.max(0, barIdx - 80)].d;
    const to     = D.candles[Math.min(D.candles.length - 1, barIdx + 20)].d;
    try {{ _chart.timeScale().setVisibleRange({{ from, to }}); }} catch(e) {{}}

    const addLine = (price, color, title) => {{
      if (!price) return;
      const pl = _candle.createPriceLine({{
        price, color, lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true, title,
      }});
      _activeLines.push(pl);
    }};
    addLine(s.bp,  '#6366f1', 'Entry');
    addLine(s.sl,  '#dc2626', 'SL');
    addLine(s.tp1, '#16a34a', 'TP1');
    addLine(s.tp2, '#16a34a', 'TP2');
  }}
  renderAnalysis(s);
}}

// ── Analysis panel ────────────────────────────────────────────────────────────
function renderAnalysis(s) {{
  if (!s) {{ document.getElementById('analysis').innerHTML = '<div class="an-empty">← Click a signal to analyse</div>'; return; }}
  const pctStr = v => v != null ? (v > 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
  const priceStr = v => v != null ? '฿' + v.toFixed(2) : '—';
  document.getElementById('analysis').innerHTML = `
    <div class="an-title">${{s.filter_type || 'Signal'}} · ${{s.date}}</div>
    <div class="an-row"><span class="an-label">Entry</span>
      <span class="an-value blue">${{priceStr(s.bp)}}</span></div>
    <div class="an-row"><span class="an-label">Stop Loss</span>
      <span class="an-value red">${{priceStr(s.sl)}} <span style="font-size:10px;opacity:.7">${{pctStr(s.sl_pct)}}</span></span></div>
    <div class="an-row"><span class="an-label">TP1 (1:${{s.rr||'?'}})</span>
      <span class="an-value green">${{priceStr(s.tp1)}} <span style="font-size:10px;opacity:.7">${{pctStr(s.tp1_pct)}}</span></span></div>
    <div class="an-row"><span class="an-label">TP2</span>
      <span class="an-value green">${{priceStr(s.tp2)}} <span style="font-size:10px;opacity:.7">${{pctStr(s.tp2_pct)}}</span></span></div>
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">Stretch</span>
      <span class="an-value ${{(s.stretch<=4)?'yellow':'red'}}">${{s.stretch?.toFixed(2)}}x ATR</span></div>
    <div class="an-row"><span class="an-label">RSM</span>
      <span class="an-value ${{s.rsm_ok?'green':'grey'}}">${{s.rsm?.toFixed(1)||'—'}}
        <span style="font-size:10px;opacity:.7">${{s.rsm_ok?'✓':'< '+D.rsm_min}}</span></span></div>
    <div class="an-row"><span class="an-label">RVol</span>
      <span class="an-value ${{s.rvol_ok?'green':'blue'}}">${{s.rvol?.toFixed(2)}}×
        <span style="font-size:10px;opacity:.7">${{s.rvol_ok?'✓':'< '+D.rvol_min+'x'}}</span></span></div>
    <div class="an-row"><span class="an-label">SMA50</span>
      <span class="an-value ${{s.regime_ok?'green':'grey'}}">${{s.regime_ok?'YES ✓':'NO ✗'}}</span></div>
    <div class="an-sep"></div>
    <div class="filter-row">
      <span class="badge ${{s.regime_ok?'pass':'fail'}}">SMA50</span>
      <span class="badge ${{s.rvol_ok?'pass':'fail'}}">RVOL</span>
      <span class="badge ${{s.rsm_ok?'pass':'fail'}}">RSM</span>
      <span class="badge ${{(s.stretch<=4)?'pass':'fail'}}">STR</span>
    </div>`;
}}

// ── Signal list ───────────────────────────────────────────────────────────────
function buildSignalList() {{
  document.getElementById('sig-count').textContent = D.signals.length;
  document.getElementById('sig-filter-info').textContent =
    `RVol>${{D.rvol_min}}x  RSM>${{D.rsm_min}}`;

  const tradeByBar = {{}};
  (D.trades||[]).forEach(t => {{
    if (!tradeByBar[t.entry_bar] || t.filter_type==='Prime') tradeByBar[t.entry_bar] = t;
  }});

  const list = document.getElementById('sig-list');
  list.innerHTML = '';
  D.signals.forEach((s, idx) => {{
    const el       = document.createElement('div');
    el.className   = 'sig-item';
    el.id          = 'sig-' + idx;
    el.dataset.date = s.date;
    const kindLabel = s.kind === 'hz' ? 'Horiz' : 'TL';
    const trade     = tradeByBar[s.i];
    const ftLabel   = s.filter_type && s.filter_type !== 'Below'
      ? `<span class="tr-filter tf-${{s.filter_type.toLowerCase()}}">${{s.filter_type}}</span> `
      : '';
    let retHtml = '';
    if (trade) {{
      const retCol = trade.ret_pct >= 0 ? '#16a34a' : '#dc2626';
      const tp1str = trade.tp1_hit ? ' TP1✓' : '';
      const tp2str = trade.tp2_hit ? ' TP2✓' : '';
      const rsn    = trade.exit_reason==='EMA10' ? 'MA10'
                   : trade.exit_reason==='End'   ? 'Open'
                   : trade.exit_reason==='BE'    ? 'BE'
                   : (trade.exit_reason||'');
      retHtml = ` <span style="color:${{retCol}};font-weight:600">${{trade.ret_pct>=0?'+':''}}${{trade.ret_pct.toFixed(1)}}%${{tp1str}}${{tp2str}} ${{rsn}}</span>`;
    }}
    el.innerHTML = `
      <div class="sig-dot" style="background:${{s.col}}"></div>
      <div class="sig-info">
        <div class="sig-date">${{ftLabel}}${{s.date}} <span style="color:#9ca3af;font-size:10px">${{kindLabel}}</span></div>
        <div class="sig-sub">฿${{s.bp.toFixed(2)}} · STR ${{s.stretch?.toFixed(1)}}x${{retHtml}}</div>
      </div>`;
    el.onclick = () => selectSignal(idx);
    list.appendChild(el);
  }});
  buildTradeSummary();
}}

// ── Trade summary ─────────────────────────────────────────────────────────────
function buildTradeSummary() {{
  const box    = document.getElementById('trade-summary');
  const trades = D.trades || [];
  if (!trades.length) {{ box.innerHTML = ''; return; }}

  const tradeRow = (lbl, cls, ts) => {{
    if (!ts.length) return '';
    const wins   = ts.filter(t=>t.win).length;
    const wr     = (wins/ts.length*100).toFixed(0);
    const avg    = ts.reduce((s,t)=>s+t.ret_pct,0)/ts.length;
    const avgCol = avg >= 0 ? '#16a34a' : '#dc2626';
    return `<div class="ts-row">
      <span><span class="tr-filter ${{cls}}">${{lbl}}</span>&nbsp; ${{ts.length}}T &nbsp; WR ${{wr}}%</span>
      <span style="color:${{avgCol}};font-weight:600">avg ${{avg>=0?'+':''}}${{avg.toFixed(1)}}%</span>
    </div>`;
  }};

  box.innerHTML = `
    <div class="ts-title">BACKTEST</div>
    ${{tradeRow('STR',   'tf-str',   trades.filter(t=>t.filter_type==='STR'))}}
    ${{tradeRow('Prime', 'tf-prime', trades.filter(t=>t.filter_type==='Prime'))}}
    ${{tradeRow('RVOL',  'tf-rvol',  trades.filter(t=>t.filter_type==='RVOL'))}}
    ${{tradeRow('RSM',   'tf-rsm',   trades.filter(t=>t.filter_type==='RSM'))}}
    ${{tradeRow('SMA50', 'tf-sma50', trades.filter(t=>t.filter_type==='SMA50'))}}`;
}}

// ── Boot ──────────────────────────────────────────────────────────────────────
const firstSignal = ALL_STOCKS.findIndex(d => d.signals.some(s => s.col === '#ff6ec7'));
(function _boot() {{
  const el = document.getElementById('chart-container');
  if (el && el.clientWidth > 0) {{ loadStock(firstSignal >= 0 ? firstSignal : 0); }}
  else {{ setTimeout(_boot, 50); }}
}})();

// ── Intraday signals sidebar section ──────────────────────────────────────────
(async function loadIntraday() {{
  try {{
    const data = await fetch('/api/signals').then(r => r.json());
    const alerts = (data.alerted_today || []).filter(s => s && (s.ticker || s));
    if (!alerts.length) return;
    const CRIT_COL = {{
      Prime:'#a21caf', STR:'#b91c1c', RVOL:'#1d4ed8', RSM:'#15803d', SMA50:'#b45309',
    }};
    const rows = alerts.map(s => {{
      const ticker = ((s.ticker || s).replace ? (s.ticker || s) : String(s)).replace('.BK','');
      const crit   = s.criteria || '';
      const col    = CRIT_COL[crit] || '#6366f1';
      const close  = s.close  ? `฿${{parseFloat(s.close).toFixed(2)}}`  : '—';
      const level  = s.level  ? `฿${{parseFloat(s.level).toFixed(2)}}`  : '—';
      return `<div class="sb-item sb-intra" title="${{ticker}} | ${{crit}} | Level ${{level}} | Price ${{close}}">
        <div class="sb-top">
          <span class="sb-ticker">${{ticker}}</span>
          <span class="sb-rsm" style="color:${{col}}">${{crit || '—'}}</span>
        </div>
        <div class="sb-bot">
          <span style="font-size:10px;color:#6b7280">Lvl ${{level}}</span>
          <span style="font-size:10px;color:#374151">${{close}}</span>
        </div>
      </div>`;
    }}).join('');
    const section = document.getElementById('intra-section');
    if (section) {{
      section.innerHTML = `<div class="sb-section-hdr sb-hdr-intra">⚡ INTRADAY (${{alerts.length}})</div>${{rows}}`;
    }}
  }} catch(e) {{ /* silent */ }}
}})();
</script>
</body>
</html>"""

    path = os.path.join(charts_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path
