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
            f'<div class="sb-section-hdr sb-hdr-sig">B BREAKOUT ({n_sig})</div>')
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

    portfolio_json = json.dumps(portfolio) if portfolio else 'null'

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
  .app {{ display:grid; grid-template-columns:190px 1fr 260px;
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
  .tf-prime   {{ background:rgba(255,110,199,.15); color:#ff6ec7; }}
  .tf-rvol   {{ background:rgba(33,150,243,.15);  color:#64b5f6; }}
  .tf-rsm    {{ background:rgba(76,175,80,.15);   color:#81c784; }}
  .tf-sma50  {{ background:rgba(255,215,64,.15);  color:#ffd740; }}
  .tf-str    {{ background:rgba(239,83,80,.15);   color:#ef9a9a; }}
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

  /* ── Nav tabs (header) ── */
  .nav-tabs {{ display:flex; gap:3px; margin-left:auto; align-items:flex-end; }}
  .nav-tab {{ padding:8px 20px; font-size:11px; letter-spacing:.08em; cursor:pointer;
              background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08);
              border-bottom:2px solid transparent; border-radius:4px 4px 0 0;
              color:var(--text); font-family:'Syne',sans-serif; font-weight:600; transition:all .15s; }}
  .nav-tab.active {{ background:rgba(0,229,204,.12); color:var(--accent); border-color:rgba(0,229,204,.25); border-bottom-color:var(--accent); font-weight:700; }}
  .nav-tab:not(.active):hover {{ background:rgba(255,255,255,.08); color:var(--white); border-color:rgba(255,255,255,.15); }}

  /* ── Backtest pane (full overlay) ── */
  #pane-backtest {{ display:none; position:fixed; top:48px; left:0; right:0; bottom:0;
                    background:var(--bg); overflow-y:auto; padding:28px 40px; z-index:50; }}
  .bt-title {{ font-family:'Syne',sans-serif; font-weight:800; font-size:22px;
               color:var(--accent); margin-bottom:8px; }}
  .bt-sub   {{ font-size:13px; color:var(--text); margin-bottom:24px; }}
  .bt-summary {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:28px; }}
  .bt-card {{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
              padding:14px 22px; min-width:140px; }}
  .bt-card-label {{ font-size:10px; color:var(--text); letter-spacing:.08em;
                    text-transform:uppercase; margin-bottom:8px; }}
  .bt-card-val   {{ font-size:24px; font-weight:700; color:var(--white); }}
  .bt-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  .bt-table th {{ padding:9px 14px; text-align:left; color:var(--text); font-size:11px;
                  letter-spacing:.07em; text-transform:uppercase; border-bottom:2px solid var(--border);
                  position:sticky; top:0; background:var(--bg); }}
  .bt-table th.r {{ text-align:right; }}
  .bt-table td {{ padding:9px 14px; border-bottom:1px solid rgba(42,46,57,.5); }}
  .bt-table td.r {{ text-align:right; }}
  .bt-table tr:hover td {{ background:rgba(0,229,204,.04); }}
  .bt-tag {{ font-size:10px; padding:2px 6px; border-radius:3px; margin-left:6px; vertical-align:middle; }}
  .bt-sig {{ background:rgba(255,110,199,.2); color:var(--pink); }}
  .bt-wtc {{ background:rgba(255,215,64,.15);  color:var(--yellow); }}
  .bt-filter-bar {{ display:flex; align-items:center; gap:10px; margin-bottom:20px;
                    padding:10px 16px; background:var(--panel); border:1px solid var(--border);
                    border-radius:8px; flex-wrap:wrap; }}
  .bt-filter-label {{ font-size:10px; letter-spacing:.08em; color:var(--text);
                      text-transform:uppercase; font-weight:600; margin-right:4px; }}
  .bt-chk {{ display:flex; align-items:center; gap:5px; cursor:pointer; font-size:11px;
              font-weight:600; padding:4px 10px; border-radius:4px; border:1px solid rgba(255,255,255,.1);
              transition:all .15s; user-select:none; }}
  .bt-chk:hover {{ border-color:rgba(255,255,255,.25); }}
  .bt-chk input {{ accent-color:var(--accent); cursor:pointer; }}

  /* ── Portfolio pane ── */
  #pane-portfolio {{ display:none; position:fixed; top:48px; left:0; right:0; bottom:0;
                     background:var(--bg); overflow-y:auto; padding:28px 40px; z-index:50; }}
  .pt-title {{ font-family:'Syne',sans-serif; font-weight:800; font-size:22px;
               color:var(--accent); margin-bottom:8px; }}
  .pt-sub   {{ font-size:13px; color:var(--text); margin-bottom:28px; }}
  .pt-cards {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:36px; }}
  .pt-card  {{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
               padding:12px 20px; min-width:140px; flex-shrink:0; }}
  .pt-card-label {{ font-size:10px; color:var(--text); letter-spacing:.08em;
                    text-transform:uppercase; margin-bottom:8px; }}
  .pt-card-val {{ font-size:22px; font-weight:700; }}
  .pt-section {{ font-family:'Syne',sans-serif; font-size:12px; font-weight:700;
                 color:var(--text); letter-spacing:.08em; text-transform:uppercase;
                 margin:0 0 14px; padding-bottom:8px; border-bottom:2px solid var(--border); }}
  .pt-curve-wrap {{ width:100%; height:180px; margin-bottom:40px; position:relative; }}
  #pt-curve {{ display:block; width:100%; height:180px; }}
  .pt-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  .pt-table th {{ padding:9px 14px; text-align:left; color:var(--text); font-size:10px;
                  letter-spacing:.07em; text-transform:uppercase; border-bottom:2px solid var(--border);
                  position:sticky; top:0; background:var(--bg); z-index:2; }}
  .pt-table th.r {{ text-align:right; }}
  .pt-table td {{ padding:8px 14px; border-bottom:1px solid rgba(42,46,57,.4); font-size:12px; }}
  .pt-table td.r {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pt-table tr:hover td {{ background:rgba(0,229,204,.04); }}
  .pt-buy  {{ border-left:3px solid var(--blue); }}
  .pt-sell {{ border-left:3px solid transparent; }}
  .pt-sell.win  {{ border-left-color:var(--green); }}
  .pt-sell.loss {{ border-left-color:var(--red); }}
  .pt-action {{ display:inline-block; font-size:9px; font-weight:700; padding:2px 7px;
                border-radius:3px; letter-spacing:.05em; }}
  .pt-act-buy  {{ background:rgba(33,150,243,.2);  color:#64b5f6; }}
  .pt-act-sell {{ background:rgba(158,158,158,.15); color:#aaa; }}
  .pt-act-win  {{ background:rgba(0,230,118,.15);  color:var(--green); }}
  .pt-act-loss {{ background:rgba(239,83,80,.15);  color:var(--red);   }}
  .pt-act-tp1  {{ background:rgba(255,215,64,.18); color:var(--yellow); }}
  .pt-act-tp2  {{ background:rgba(255,152,0,.18);  color:var(--orange); }}
  .pt-act-open {{ background:rgba(0,229,204,.12);  color:var(--accent); }}
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">◈ BREAKOUT SCANNER</div>
    <div class="hticker" id="h-ticker">← Select a stock</div>
    <div class="hinfo"   id="h-info"></div>
    <div class="hrsm"    id="h-rsm"></div>
    <div class="hdate">{date_str.replace('_','-')} · {total} stocks · <span style="color:var(--pink)">{n_sig} signals</span> · <span style="color:var(--yellow)">{n_wtc} watching</span></div>
    <div class="nav-tabs">
      <div class="nav-tab active" id="nav-chart"     onclick="switchNav('chart')">CHART</div>
      <div class="nav-tab"        id="nav-backtest"  onclick="switchNav('backtest')">BACKTEST</div>
      <div class="nav-tab"        id="nav-portfolio" onclick="switchNav('portfolio')">PORTFOLIO</div>
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

<!-- BACKTEST pane (fixed overlay, hidden by default) -->
<div id="pane-backtest">
  <div style="max-width:1080px;margin:0 auto">
  <div class="bt-title">BACKTEST RESULTS</div>
  <div class="bt-sub" id="bt-sub">Loading...</div>
  <div class="bt-summary" id="bt-cards"></div>

  <!-- Strategy filter bar -->
  <div class="bt-filter-bar" id="bt-filter-bar">
    <span class="bt-filter-label">INCLUDE:</span>
    <label class="bt-chk tf-prime"><input type="checkbox" value="Prime" checked onchange="applyBtFilter()"> Prime</label>
    <label class="bt-chk tf-str"><input type="checkbox" value="STR" onchange="applyBtFilter()"> STR</label>
    <label class="bt-chk tf-rvol"><input type="checkbox" value="RVOL" onchange="applyBtFilter()"> RVOL</label>
    <label class="bt-chk tf-rsm"><input type="checkbox" value="RSM" onchange="applyBtFilter()"> RSM</label>
    <label class="bt-chk tf-sma50"><input type="checkbox" value="SMA50" onchange="applyBtFilter()"> SMA50</label>
  </div>

  <table class="bt-table">
    <thead>
      <tr>
        <th>Ticker</th>
        <th class="r">RSM</th>
        <th class="r">Trades</th>
        <th class="r">WR%</th>
        <th class="r">Avg Win</th>
        <th class="r">Avg Loss</th>
        <th class="r">Avg Stretch</th>
        <th class="r">PnL%</th>
      </tr>
    </thead>
    <tbody id="bt-tbody"></tbody>
  </table>
  </div>
</div>

<!-- PORTFOLIO pane -->
<div id="pane-portfolio">
  <div style="max-width:1080px;margin:0 auto">
  <div class="pt-title">PORTFOLIO SIMULATION</div>
  <div class="pt-sub" id="pt-sub">Loading...</div>

  <div class="pt-cards" id="pt-cards"></div>

  <div class="pt-section">EQUITY CURVE</div>
  <div class="pt-curve-wrap">
    <canvas id="pt-curve"></canvas>
  </div>

  <div class="pt-section">TRADE LOG — chronological buy / sell with running balance</div>
  <table class="pt-table">
    <thead>
      <tr>
        <th style="width:110px">Date</th>
        <th style="width:60px">Action</th>
        <th style="width:110px">Ticker</th>
        <th class="r">Stretch</th>
        <th class="r">Sizing (฿)</th>
        <th class="r">Cash (฿)</th>
        <th>Exit Reason</th>
        <th class="r">Trade PnL (฿)</th>
        <th class="r">Return%</th>
        <th class="r">Balance (฿)</th>
      </tr>
    </thead>
    <tbody id="pt-tbody"></tbody>
  </table>

  <div class="pt-section" id="skip-section" style="display:none">
    SKIPPED SIGNALS — positions rejected by portfolio rules
    <span id="skip-toggle" onclick="toggleSkipLog()"
      style="cursor:pointer;font-size:10px;color:var(--accent);margin-left:10px">[show]</span>
  </div>
  <div id="skip-log-wrap" style="display:none;margin-bottom:32px">
    <table class="pt-table">
      <thead><tr>
        <th style="width:110px">Date</th>
        <th style="width:110px">Ticker</th>
        <th>Reason</th>
      </tr></thead>
      <tbody id="skip-tbody"></tbody>
    </table>
  </div>
  </div>
</div>

<script>
// ── All stock data ─────────────────────────────────────────────────────────────
const ALL_STOCKS = {all_stocks_json};
const BT         = {backtest_json};
const PT         = {portfolio_json};
let D = null;
let currentStockIdx = null;
let selectedSigIdx  = null;

// ── Nav tab switching ─────────────────────────────────────────────────────────
function switchNav(name) {{
  ['chart','backtest','portfolio'].forEach(n => {{
    document.getElementById('nav-'+n).classList.toggle('active', n===name);
  }});
  document.getElementById('pane-backtest').style.display  = name==='backtest'  ? 'block' : 'none';
  document.getElementById('pane-portfolio').style.display = name==='portfolio' ? 'block' : 'none';
  if(name==='backtest')  renderBacktest();
  if(name==='portfolio') renderPortfolio();
}}

function goToChart(idx) {{
  switchNav('chart');
  loadStock(idx);
  document.getElementById('sb-'+idx)?.scrollIntoView({{block:'center'}});
}}

// ── Portfolio tab ─────────────────────────────────────────────────────────────
function renderPortfolio() {{
  if(document.getElementById('pt-tbody').children.length) return;
  if(!PT) {{
    document.getElementById('pt-sub').textContent = 'No portfolio data available.';
    return;
  }}
  const p = PT;

  document.getElementById('pt-sub').textContent =
    `Max ${{p.max_positions}} concurrent positions  ·  ${{p.n_taken}} trades  ·  ${{p.n_skipped}} skipped`;

  // ── Summary cards ────────────────────────────────────────────────────────
  const retCol = p.total_ret_pct >= 0 ? 'var(--green)' : 'var(--red)';
  const cards = [
    {{ label:'Start Capital', val:'฿'+p.start_capital.toLocaleString(),                          col:'var(--white)'  }},
    {{ label:'Final Equity',  val:'฿'+Math.round(p.final_equity).toLocaleString(),               col: retCol         }},
    {{ label:'Total Return',  val:(p.total_ret_pct>=0?'+':'')+p.total_ret_pct+'%',               col: retCol         }},
    {{ label:'Win Rate',      val:p.win_rate+'%',                                                 col:'var(--green)'  }},
    {{ label:'Avg Win',       val:(p.avg_win>=0?'+':'')+p.avg_win+'%',                           col:'var(--green)'  }},
    {{ label:'Avg Loss',      val:p.avg_loss+'%',                                                 col:'var(--red)'    }},
    {{ label:'Max Drawdown',  val:'-'+p.max_drawdown+'%',                                         col:'var(--red)'    }},
    {{ label:'Trades Taken',  val:p.n_taken+' ('+p.n_wins+'W / '+p.n_losses+'L)',               col:'var(--white)'  }},
  ];
  document.getElementById('pt-cards').innerHTML = cards.map(c =>
    `<div class="pt-card">
       <div class="pt-card-label">${{c.label}}</div>
       <div class="pt-card-val" style="color:${{c.col}}">${{c.val}}</div>
     </div>`).join('');

  // ── Equity curve ─────────────────────────────────────────────────────────
  const canvas = document.getElementById('pt-curve');
  const ctx    = canvas.getContext('2d');
  const pts    = p.equity_curve;
  // Size to the wrapper, not canvas default
  const wrap   = canvas.parentElement;
  canvas.width  = wrap.clientWidth  || 1000;
  canvas.height = wrap.clientHeight || 180;
  const W = canvas.width, H = canvas.height;
  const PAD = {{t:20, r:24, b:36, l:80}};

  const eqs  = pts.map(q => q.equity);
  const minEq = Math.min(...eqs), maxEq = Math.max(...eqs);
  const range = maxEq - minEq || 1;
  const xS = i  => PAD.l + (i / (pts.length - 1)) * (W - PAD.l - PAD.r);
  const yS = v  => PAD.t + (1 - (v - minEq) / range) * (H - PAD.t - PAD.b);

  // Horizontal grid lines
  ctx.strokeStyle = '#2a2e39'; ctx.lineWidth = 1;
  for(let g = 0; g <= 4; g++) {{
    const y   = PAD.t + g * (H - PAD.t - PAD.b) / 4;
    const val = maxEq - g * range / 4;
    ctx.beginPath(); ctx.moveTo(PAD.l, y); ctx.lineTo(W - PAD.r, y); ctx.stroke();
    ctx.fillStyle = '#9598a1'; ctx.font = '10px DM Mono,monospace'; ctx.textAlign = 'right';
    ctx.fillText('฿' + Math.round(val).toLocaleString(), PAD.l - 6, y + 4);
  }}

  // Start capital dashed reference line
  const capY = yS(p.start_capital);
  ctx.setLineDash([5, 4]); ctx.strokeStyle = '#444'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(PAD.l, capY); ctx.lineTo(W - PAD.r, capY); ctx.stroke();
  ctx.setLineDash([]);

  // Gradient fill
  const aboveCapital = p.final_equity >= p.start_capital;
  const fillColor    = aboveCapital ? 'rgba(0,230,118,' : 'rgba(239,83,80,';
  const grad = ctx.createLinearGradient(0, PAD.t, 0, H - PAD.b);
  grad.addColorStop(0, fillColor + '0.2)');
  grad.addColorStop(1, fillColor + '0.02)');
  ctx.beginPath();
  pts.forEach((pt, i) => i === 0 ? ctx.moveTo(xS(i), yS(pt.equity)) : ctx.lineTo(xS(i), yS(pt.equity)));
  ctx.lineTo(xS(pts.length - 1), H - PAD.b);
  ctx.lineTo(xS(0), H - PAD.b);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  // Main line
  const lineColor = aboveCapital ? '#00e676' : '#ef5350';
  ctx.strokeStyle = lineColor; ctx.lineWidth = 2;
  ctx.beginPath();
  pts.forEach((pt, i) => i === 0 ? ctx.moveTo(xS(i), yS(pt.equity)) : ctx.lineTo(xS(i), yS(pt.equity)));
  ctx.stroke();

  // Date labels: first, middle, last
  ctx.fillStyle = '#9598a1'; ctx.font = '10px DM Mono,monospace'; ctx.textAlign = 'center';
  [[0, 'left'], [Math.floor(pts.length/2), 'center'], [pts.length-1, 'right']].forEach(([i, align]) => {{
    if(i < pts.length) {{
      ctx.textAlign = align;
      const x = align==='left' ? PAD.l : align==='right' ? W-PAD.r : xS(i);
      ctx.fillText(pts[i].date, x, H - 6);
    }}
  }});

  // ── Trade log (chronological BUY / TP1 / TP2 / SELL events) ────────────
  // Build ticker → sidebar index map for click-through
  const tickerIdx = {{}};
  ALL_STOCKS.forEach((s, i) => {{ tickerIdx[s.ticker] = i; }});

  const tbody = document.getElementById('pt-tbody');
  let separatorAdded = false;
  tbody.innerHTML = p.events.map((e, rowI) => {{
    const isBuy  = e.action === 'BUY';
    const isOpen = e.action === 'OPEN';
    const isTp1  = !isBuy && !isOpen && e.reason.startsWith('TP1');
    const isTp2  = !isBuy && !isOpen && e.reason.startsWith('TP2');
    const isWin  = !isBuy && !isOpen && e.pnl > 0;

    // Insert separator before first OPEN row
    let separator = '';
    if (isOpen && !separatorAdded) {{
      separatorAdded = true;
      separator = `<tr style="height:1px;background:var(--accent);opacity:.25">
        <td colspan="8" style="padding:0;font-size:10px;color:var(--accent);letter-spacing:.08em;text-transform:uppercase;padding:8px 14px 4px;opacity:1;background:var(--bg)">
          ▸ OPEN POSITIONS — still holding
        </td>
      </tr>`;
    }}

    const rowCls = isBuy ? 'pt-buy' : isOpen ? 'pt-buy' : isWin ? 'pt-sell win' : 'pt-sell loss';
    const actCls = isBuy  ? 'pt-act-buy'
                 : isOpen ? 'pt-act-open'
                 : isTp1  ? 'pt-act-tp1'
                 : isTp2  ? 'pt-act-tp2'
                 : isWin  ? 'pt-act-win' : 'pt-act-loss';
    const actLbl = isBuy ? 'BUY' : isOpen ? 'OPEN' : isTp1 ? 'TP1' : isTp2 ? 'TP2' : 'SELL';
    const pnlStr = (isBuy||isOpen) ? '—' : (e.pnl >= 0 ? '+' : '') + Math.round(e.pnl).toLocaleString();
    const retStr = (isBuy||isOpen) ? '—' : (e.ret_pct >= 0 ? '+' : '') + e.ret_pct + '%';
    const retCol = (isBuy||isOpen) ? 'var(--text)' : isTp1||isTp2||isWin ? 'var(--green)' : 'var(--red)';
    const reasonStr = isBuy ? '—' : isOpen ? 'Still holding at period end'
                    : isTp1 ? '30% at TP1' : isTp2 ? '30% at TP2' : e.reason || '—';

    // Clickable ticker — jump to chart and highlight matching signal/trade
    const sidx = tickerIdx[e.ticker_full];
    const tickerClick = sidx !== undefined
      ? `onclick="ptGoToChart(${{sidx}}, '${{e.ticker}}', '${{e.date}}')" style="cursor:pointer;text-decoration:underline;text-decoration-color:var(--accent)"`
      : '';

    return separator + `<tr class="${{rowCls}}" id="pt-row-${{rowI}}">
      <td style="color:var(--text)">${{e.date}}</td>
      <td><span class="pt-action ${{actCls}}">${{actLbl}}</span></td>
      <td ${{tickerClick}} style="color:var(--white);font-weight:600">${{e.ticker}}${{sidx!==undefined ? ' <span style="font-size:9px;color:var(--accent);opacity:.6">→</span>' : ''}}</td>
      <td class="r" style="color:${{isBuy&&e.stretch>4?'var(--red)':isBuy&&e.stretch>2?'var(--yellow)':'var(--text)'}}">${{isBuy&&e.stretch?e.stretch+'x':'—'}}</td>
      <td class="r" style="color:var(--text)">฿${{Math.round(e.sizing).toLocaleString()}}</td>
      <td class="r" style="color:var(--text)">฿${{Math.round(e.cash_after).toLocaleString()}}</td>
      <td style="color:var(--text);font-size:11px">${{reasonStr}}</td>
      <td class="r" style="color:${{retCol}}">${{pnlStr}}</td>
      <td class="r" style="color:${{retCol}}">${{retStr}}</td>
      <td class="r" style="color:var(--white);font-weight:500">฿${{Math.round(e.balance).toLocaleString()}}</td>
    </tr>`;
  }}).join('');

  // ── Skip log ────────────────────────────────────────────────────────────────
  const skipLog = p.skip_log || [];
  if(skipLog.length) {{
    document.getElementById('skip-section').style.display = '';
    const sTbody = document.getElementById('skip-tbody');
    sTbody.innerHTML = skipLog.map(([date, ticker, reason]) => {{
      const rCol = reason.startsWith('max_pos') ? 'var(--yellow)'
                 : reason.startsWith('dup')     ? 'var(--text)'
                 : 'var(--red)';
      return `<tr>
        <td style="color:var(--text)">${{date}}</td>
        <td style="color:var(--white);font-weight:600">${{ticker}}</td>
        <td style="color:${{rCol}};font-size:11px">${{reason}}</td>
      </tr>`;
    }}).join('');
  }}
}}

function toggleSkipLog() {{
  const wrap = document.getElementById('skip-log-wrap');
  const btn  = document.getElementById('skip-toggle');
  const open = wrap.style.display === 'none';
  wrap.style.display = open ? '' : 'none';
  btn.textContent    = open ? '[hide]' : '[show]';
}}

function ptGoToChart(idx, ticker, date) {{
  switchNav('chart');
  loadStock(idx);
  document.getElementById('sb-'+idx)?.scrollIntoView({{block:'center'}});
  // Highlight the signal on the right date
  setTimeout(() => {{
    const sigs = document.querySelectorAll('.sig-item');
    sigs.forEach(el => {{
      if(el.dataset.date && el.dataset.date.startsWith(date)) {{
        el.click();
        el.scrollIntoView({{block:'nearest'}});
      }}
    }});
  }}, 120);
}}

// ── Active filter types (default: Prime only) ────────────────────────────────
let activeFilters = new Set(['Prime']);

function getActiveFilters() {{
  return [...document.querySelectorAll('#bt-filter-bar input[type=checkbox]:checked')]
    .map(cb => cb.value);
}}

function mergeByType(row, types) {{
  let n=0, wins=0, sumWin=0, nWin=0, sumLoss=0, nLoss=0, sumStretch=0, nStr=0, pnlCap=0;
  types.forEach(ft => {{
    const d = row.by_type[ft];
    if(!d) return;
    n      += d.n;
    const w = Math.round(d.wr / 100 * d.n);
    wins   += w;
    if(d.avg_win  != null) {{ sumWin  += d.avg_win  * w;       nWin  += w; }}
    if(d.avg_loss != null) {{ sumLoss += d.avg_loss * (d.n-w); nLoss += (d.n-w); }}
    if(d.avg_stretch != null) {{ sumStretch += d.avg_stretch * d.n; nStr += d.n; }}
    pnlCap += (d.pnl_capital || 0);
  }});
  return {{
    trades:     n,
    wr:         n ? +(wins/n*100).toFixed(1) : 0,
    avg_win:    nWin  ? +(sumWin/nWin).toFixed(2)    : null,
    avg_loss:   nLoss ? +(sumLoss/nLoss).toFixed(2)  : null,
    avg_stretch:nStr  ? +(sumStretch/nStr).toFixed(2): null,
    pnl_pct:    +pnlCap.toFixed(2),
  }};
}}

function applyBtFilter() {{
  const types = getActiveFilters();
  const b = BT;

  let totTrades=0, totWins=0, sumW=0, nW=0, sumL=0, nL=0, totPnlCap=0, nStocks=0;
  b.rows.forEach(r => {{
    const m = mergeByType(r, types);
    if(!m.trades) return;
    nStocks++;
    totTrades += m.trades;
    const w = Math.round(m.wr/100*m.trades);
    totWins   += w;
    if(m.avg_win  != null) {{ sumW += m.avg_win  * w; nW += w; }}
    if(m.avg_loss != null) {{ const l = m.trades-w; sumL += m.avg_loss*l; nL += l; }}
    totPnlCap += m.pnl_pct;
  }});
  const wr     = totTrades ? +(totWins/totTrades*100).toFixed(1) : 0;
  const avgWin = nW ? +(sumW/nW).toFixed(2) : 0;
  const avgLoss= nL ? +(sumL/nL).toFixed(2) : 0;
  // Avg PnL per stock (return on 100k capital averaged across active stocks)
  const avgPnl = nStocks ? +(totPnlCap/nStocks).toFixed(2) : 0;

  document.getElementById('bt-sub').textContent =
    `${{b.n_stocks}} stocks · ${{totTrades}} trades · WR ${{wr}}% · ` +
    `Avg win ${{avgWin>=0?'+':''}}${{avgWin}}% · Avg loss ${{avgLoss}}%`;

  const cards = [
    {{ label:'Stocks',        val: b.n_stocks }},
    {{ label:'Trades',        val: totTrades }},
    {{ label:'Win Rate',      val: wr+'%' }},
    {{ label:'Avg Win',       val: (avgWin>=0?'+':'')+avgWin+'%' }},
    {{ label:'Avg Loss',      val: avgLoss+'%' }},
    {{ label:'Avg PnL/Stock', val: (avgPnl>=0?'+':'')+avgPnl+'%' }},
  ];
  document.getElementById('bt-cards').innerHTML = cards.map(c => `
    <div class="bt-card">
      <div class="bt-card-label">${{c.label}}</div>
      <div class="bt-card-val" style="color:${{
        c.label==='Win Rate'||c.label==='Avg Win' ? 'var(--green)' :
        c.label==='Avg Loss' ? 'var(--red)' :
        c.label==='Avg PnL/Stock' ? (avgPnl>=0?'var(--green)':'var(--red)') :
        'var(--white)'
      }}">${{c.val}}</div>
    </div>`).join('');

  // Rebuild rows with merged stats, sort by pnl_pct descending
  const merged = b.rows.map(r => ({{ ...r, ...mergeByType(r, types) }}))
    .filter(r => r.trades > 0)
    .sort((a,b) => b.pnl_pct - a.pnl_pct);

  const tbody = document.getElementById('bt-tbody');
  tbody.innerHTML = merged.map(r => {{
    const pnlCol = r.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)';
    const sigTag = r.has_signal  ? '<span class="bt-tag bt-sig">B</span>' : '';
    const wtcTag = r.has_pending ? '<span class="bt-tag bt-wtc">W</span>'  : '';
    const click  = r.idx >= 0 ? `onclick="goToChart(${{r.idx}})" style="cursor:pointer"` : '';
    const strCol = r.avg_stretch>4?'var(--red)':r.avg_stretch>2?'var(--yellow)':'var(--text)';
    return `<tr ${{click}}>
      <td><b style="color:var(--white)">${{r.ticker}}</b>${{sigTag}}${{wtcTag}}
        ${{r.idx>=0?'<span style="font-size:9px;color:var(--accent);margin-left:6px;opacity:.6">→ chart</span>':''}}
      </td>
      <td class="r" style="color:var(--yellow)">${{r.rsm}}</td>
      <td class="r">${{r.trades}}</td>
      <td class="r">${{r.wr}}%</td>
      <td class="r" style="color:var(--green)">${{r.avg_win!=null?(r.avg_win>=0?'+':'')+r.avg_win+'%':'—'}}</td>
      <td class="r" style="color:var(--red)">${{r.avg_loss!=null?r.avg_loss+'%':'—'}}</td>
      <td class="r" style="color:${{strCol}}">${{r.avg_stretch!=null?r.avg_stretch+'x':'—'}}</td>
      <td class="r" style="color:${{pnlCol}};font-weight:600">${{r.pnl_pct>=0?'+':''}}${{r.pnl_pct}}%</td>
    </tr>`;
  }}).join('');
}}

function renderBacktest() {{
  if(document.getElementById('bt-tbody').children.length) return; // already built
  applyBtFilter(); // initial render with Prime checked
}}

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
  const pHMain = 0.72, pHRsm = 0.13, pHVol = 0.13;
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
  ctx.fillStyle='rgba(255,215,64,.85)'; ctx.font='bold 9px DM Mono'; ctx.textAlign='left';
  ctx.fillText(D.rsm_min, W-MARGIN.r+3, yRsmMin+3);

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
  // Big circle on selected signal
  ctx.fillStyle=s.col;
  ctx.beginPath(); ctx.arc(x, yOf(s.bar_y,0)-10, 7, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle='white'; ctx.lineWidth=1.5; ctx.stroke();

  // Highlight matching trade exit arrows
  // Try Full trade first, fall back to any trade at that bar
  const trade = (D.trades||[]).find(t => t.entry_bar === s.i && t.filter_type === 'Prime')
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
    if(!tradeByBar[t.entry_bar] || t.filter_type==='Prime') tradeByBar[t.entry_bar] = t;
  }});

  const list = document.getElementById('sig-list');
  list.innerHTML = '';
  D.signals.forEach((s, idx) => {{
    const el = document.createElement('div');
    el.className = 'sig-item';
    el.id = 'sig-' + idx;
    el.dataset.date = s.date;  // for portfolio click-through
    const kindLabel = s.kind === 'hz' ? 'Horiz' : 'TL';
    const trade = tradeByBar[s.i];
    const dotHtml = `<div class="sig-dot" style="background:${{s.col}}"></div>`;
    const ftLabel = s.filter_type && s.filter_type !== 'Below'
      ? `<span class="tr-filter tf-${{s.filter_type.toLowerCase()}}" style="font-size:9px;padding:1px 4px;margin-right:3px">${{s.filter_type}}</span>`
      : '';
    let retHtml = '';
    if(trade) {{
      const retCol = trade.ret_pct >= 0 ? '#00e676' : '#ef5350';
      const tp1str = trade.tp1_hit ? ' TP1✓' : '';
      const tp2str = trade.tp2_hit ? ' TP2✓' : '';
      const rsn    = trade.exit_reason==='EMA10' ? 'MA10' : (trade.exit_reason||'');
      retHtml = ` <span style="color:${{retCol}};font-weight:600">${{trade.ret_pct>=0?'+':''}}${{trade.ret_pct.toFixed(1)}}%${{tp1str}}${{tp2str}} ${{rsn}}</span>`;
    }}
    el.innerHTML = `
      ${{dotHtml}}
      <div class="sig-info">
        <div class="sig-date">${{ftLabel}}${{s.date}} <span style="color:#888;font-size:9px">${{kindLabel}}</span></div>
        <div class="sig-sub">฿${{s.bp.toFixed(2)}} · STR ${{s.stretch?.toFixed(1)}}x${{retHtml}}</div>
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

  function tradeRow(lbl, cls, ts) {{
    if(!ts.length) return '';
    const wins   = ts.filter(t=>t.win).length;
    const wr     = (wins/ts.length*100).toFixed(0);
    const avg    = ts.reduce((s,t)=>s+t.ret_pct,0)/ts.length;
    const avgCol = avg >= 0 ? '#00e676' : '#ef5350';
    return `<div class="ts-row">
      <span><span class="tr-filter ${{cls}}" style="margin-right:5px">${{lbl}}</span>
        ${{ts.length}}T &nbsp; WR${{wr}}%</span>
      <span style="color:${{avgCol}};font-weight:600">avg ${{avg>=0?'+':''}}${{avg.toFixed(1)}}%</span>
    </div>`;
  }}

  let rows = '';
  rows += tradeRow('STR',   'tf-str',   trades.filter(t=>t.filter_type==='STR'));
  rows += tradeRow('Prime', 'tf-prime', trades.filter(t=>t.filter_type==='Prime'));
  rows += tradeRow('RVOL',  'tf-rvol',  trades.filter(t=>t.filter_type==='RVOL'));
  rows += tradeRow('RSM',   'tf-rsm',   trades.filter(t=>t.filter_type==='RSM'));
  rows += tradeRow('SMA50', 'tf-sma50', trades.filter(t=>t.filter_type==='SMA50'));

  if(rows) box.innerHTML = `<div class="ts-title">BACKTEST SUMMARY</div>${{rows}}`;
  else box.innerHTML = '';
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
    <div class="an-sep"></div>
    <div class="an-row"><span class="an-label">Stretch (×ATR)</span>
      <span class="an-value" style="color:${{s.stretch>4?'var(--red)':'var(--green)'}}">${{s.stretch?.toFixed(2)}}x
        <span style="font-size:10px">${{s.stretch>4?'✗':'✓'}}</span>
      </span></div>
    <div class="an-row"><span class="an-label">RSM</span>
      <span class="an-value ${{s.rsm_ok?'green':'yellow'}}">${{s.rsm?.toFixed(1)}}
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
