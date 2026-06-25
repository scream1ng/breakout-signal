/* bs-views.jsx — Terminal-style views. Data via props; helpers from window.BS.
 * Exports: Topbar, NavRail, ChartWorkspace, RightPanel, BacktestView,
 * PortfolioView, JobsView, HelpDrawer, RunModal. */
const { fmt0, fmt1, fmt2, fmtDatetime, tickerText, CC, CRIT_COLOR } = window.BS;

/* one shared grid so columns line up across every tab: Symbol | Level | Last | RVol | RSM | STR */
const GRID = '1fr 56px 58px 42px 30px 44px';
const HILITE = { Prime: 1, RVOL: 1 };   // criteria that tint signal rows (Alerts/EOD)
/* shared column widths for the two portfolio tables so they align */
const PF_COLS = (
  <colgroup>
    <col style={{ width: '9%' }} /><col style={{ width: '13%' }} /><col style={{ width: '12%' }} /><col style={{ width: '11%' }} />
    <col style={{ width: '12%' }} /><col style={{ width: '12%' }} /><col style={{ width: '19%' }} /><col style={{ width: '12%' }} />
  </colgroup>
);

const keyOf = (s) => tickerText(s);

/* ═══════════════════════ TOPBAR + NAV RAIL ═══════════════════════ */
function LogoMark({ size = 22 }) {
  return (
    <svg className="tb-mark" viewBox="0 0 28 28" width={size} height={size} fill="none" aria-hidden="true"
      stroke="#1848c8" strokeLinecap="round" strokeLinejoin="round">
      {/* dashed resistance line being broken */}
      <line x1="3.5" y1="16" x2="24.5" y2="16" strokeWidth="1.7" strokeDasharray="2 2.6" opacity="0.5" />
      {/* upward breakout arrow punching through */}
      <path d="M14 24 L14 6.5" strokeWidth="2.6" />
      <path d="M8 12 L14 5.5 L20 12" strokeWidth="2.6" />
    </svg>
  );
}

function Topbar({ schedulerRunning, date, onRefresh, refreshing, onHelp }) {
  return (
    <div className="tb">
      <div className="tb-logo"><LogoMark /> Breakout Signal</div>
      <span className="tb-set">Thai SET</span>
      <div className="tb-r">
        <span className={`tb-dot ${schedulerRunning ? '' : 'off'}`}></span>
        <span>{schedulerRunning ? 'Scheduler running' : 'Scheduler stopped'}</span>
        <span className="tb-sep">·</span>
        <span className="mono">{date}</span>
        <button className={`tb-btn ${refreshing ? 'spin' : ''}`} onClick={onRefresh}><span className="ri">↻</span> Refresh</button>
        <button className="tb-btn tb-help" onClick={onHelp}>FAQ</button>
      </div>
    </div>
  );
}

function NavIcon({ id }) {
  const p = { width: 21, height: 21, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' };
  if (id === 'chart')
    return (<svg {...p}><line x1="7" y1="4" x2="7" y2="20"/><rect x="4.5" y="8" width="5" height="7" rx="1"/><line x1="16" y1="3" x2="16" y2="21"/><rect x="13.5" y="7" width="5" height="9" rx="1"/></svg>);
  if (id === 'backtest')
    return (<svg {...p}><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 3 3 7 7 7"/><polyline points="12 8 12 12 15 14"/></svg>);
  if (id === 'portfolio')
    return (<svg {...p}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="3" y1="12.5" x2="21" y2="12.5"/></svg>);
  return (<svg {...p}><line x1="8" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="20" y2="12"/><line x1="8" y1="18" x2="20" y2="18"/><polyline points="3 5.5 4 6.5 5.5 4.5"/><polyline points="3 11.5 4 12.5 5.5 10.5"/><circle cx="4" cy="18" r="0.6" fill="currentColor"/></svg>);
}

const NAV = [
  { id: 'chart', label: 'Chart' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'jobs', label: 'Jobs' },
];

function NavRail({ active, onNav, jobs }) {
  const dotCls = (s) => s === 'running' ? 'rn' : (s === 'failed' || s === 'stale') ? 'fl' : s === 'completed' ? 'ok' : 'ny';
  return (
    <div className="nr">
      {NAV.map(n =>
        <div key={n.id} className={`nr-i ${active === n.id ? 'act' : ''}`} onClick={() => onNav(n.id)}>
          <span className="nr-ic"><NavIcon id={n.id} /></span>
          <span className="nr-lb">{n.label}</span>
        </div>)}
      <div className="nr-spacer"></div>
      {(jobs || []).map((j, i) =>
        <div key={i} className="nr-job" title={`${j.label}: ${j.status}`}>
          <span className={`nr-job-dot ${dotCls(j.status)}`}></span>
        </div>)}
      <div style={{ height: 10 }}></div>
    </div>
  );
}

/* ═══════════════════════ RIGHT PANEL (tabbed lists) ═══════════════════════ */
/* derive criteria for a broken-out watchlist row (no criteria field on the item) */
function classify(s) {
  if ((s.stretch || 0) > 4) return 'STR';
  if (s.rvol >= 2 && s.rsm >= 80) return 'Prime';
  if (s.rvol >= 2) return 'RVOL';
  if (s.rsm >= 80) return 'RSM';
  return 'SMA50';
}

/* shared list row — Symbol | Level | Last | RVol | RSM | STR.
 * badgeCrit = criteria chip to show (or null); tintCrit = criteria to tint the row by (or null). */
function Row({ s, selected, onSelect, lvl, rvol, badgeCrit, tintCrit, fk }) {
  const str = s.stretch ?? null;
  const cc = tintCrit ? CRIT_COLOR[tintCrit] : null;
  const style = { gridTemplateColumns: GRID };
  if (cc) { style.background = cc + (selected ? '3a' : '20'); style.boxShadow = `inset 3px 0 0 ${cc}`; }
  else if (selected) { style.background = 'var(--blue-soft)'; style.boxShadow = 'inset 3px 0 0 var(--blue)'; }
  return (
    <button className={`wl-row ${selected ? 'sel' : ''} ${fk ? 'fk' : ''}`} style={style} onClick={() => onSelect(s)}>
      <span className={`wl-tk ${fk ? 'red' : ''}`}>{tickerText(s)}{badgeCrit && <span className={`bg ${CC[badgeCrit] || ''}`}>{badgeCrit}</span>}</span>
      <span className="wl-px mono b">{lvl != null ? fmt2(lvl) : '—'}</span>
      <span className="wl-px mono">{fmt2(s.close)}</span>
      <span className={`wl-rsm mono ${rvol >= 2 ? 'g' : 'dm'}`}>{rvol != null ? fmt1(rvol) + '×' : '—'}</span>
      <span className={`wl-rsm mono ${s.rsm >= 80 ? 'g' : 'dm'}`}>{s.rsm != null ? fmt0(s.rsm) : '—'}</span>
      <span className={`wl-rsm mono ${(str || 0) > 4 ? 'r' : 'dm'}`}>{str != null ? fmt1(str) + '×' : '—'}</span>
    </button>
  );
}

/* watchlist: criteria derived (no field on the item) + tint only when it broke */
function WatchRow({ s, selected, onSelect }) {
  const crit = s.broke ? (s.criteria || classify(s)) : null;
  return <Row s={s} selected={selected} onSelect={onSelect}
    lvl={s.levels?.[0]?.level ?? s.level ?? null} rvol={s.rvol ?? null}
    badgeCrit={crit} tintCrit={crit} />;
}

/* signals (alerts/eod/fakeouts): show criteria chip always, tint only Prime/RVOL */
function SignalRow({ s, selected, onSelect, fk }) {
  const crit = s.criteria || s.filter_type;
  return <Row s={s} selected={selected} onSelect={onSelect}
    lvl={s.level ?? s.bp ?? null} rvol={s.proj_rvol_now ?? s.proj_rvol ?? s.rvol ?? null}
    badgeCrit={crit} tintCrit={!fk && HILITE[crit] ? crit : null} fk={fk} />;
}

function RightPanel({ selected, onSelect, watchlist, intraday, fakeouts, eod }) {
  const [tab, setTab] = React.useState('watch');
  const items = watchlist?.items || [];
  const wlGroups = watchlist?.groups || {};
  const GROUP_ORDER = ['> MA10', '> MA20', '> MA50', 'Other'];
  const tagCls = (g) => g.includes('10') ? 'g10' : g.includes('20') ? 'g20' : g.includes('50') ? 'g50' : 'go';
  const copyStr = watchlist?.copy_str || '';
  const counts = { watch: items.length, alerts: (intraday || []).length, fk: (fakeouts || []).length, eod: (eod || []).length };
  const selKey = selected ? keyOf(selected) : null;
  const [copied, setCopied] = React.useState(false);
  const copyWL = () => { navigator.clipboard?.writeText(copyStr).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 1500); };

  const TABS = [
    { id: 'watch', label: 'Watchlist' },
    { id: 'alerts', label: 'Alerts' },
    { id: 'fk', label: 'Fakeouts' },
    { id: 'eod', label: 'EOD' },
  ];

  return (
    <div className="rp">
      <div className="rp-tabs">
        {TABS.map(t =>
          <button key={t.id} className={`rp-tab ${tab === t.id ? 'on' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}<span className="rp-ct">{counts[t.id]}</span>
          </button>)}
      </div>

      <div className="rp-colhead" style={{ gridTemplateColumns: GRID }}>
        <span>Symbol</span><span className="r">Level</span><span className="r">Last</span><span className="r">RVol</span><span className="r">RSM</span><span className="r">STR</span>
      </div>

      <div className="rp-scroll">
        {tab === 'watch' && items.length === 0 && <div className="rp-empty">No watchlist</div>}
        {tab === 'watch' && GROUP_ORDER.map(g => {
          const rows = wlGroups[g] || [];
          if (!rows.length) return null;
          return (
            <React.Fragment key={g}>
              <div className="wl-grp"><span className={`lbl ${tagCls(g)}`}>{g}</span><span className="c">{rows.length}</span></div>
              {rows.map((s, i) => <WatchRow key={g + i} s={s} selected={selKey === keyOf(s)} onSelect={onSelect} />)}
            </React.Fragment>
          );
        })}
        {tab === 'alerts' && (intraday || []).map((s, i) => <SignalRow key={i} s={s} selected={selKey === keyOf(s)} onSelect={onSelect} />)}
        {tab === 'alerts' && (intraday || []).length === 0 && <div className="rp-empty">No intraday alerts</div>}
        {tab === 'fk' && (fakeouts || []).map((s, i) => <SignalRow key={i} s={s} selected={selKey === keyOf(s)} onSelect={onSelect} fk />)}
        {tab === 'fk' && (fakeouts || []).length === 0 && <div className="rp-empty">No fakeouts today</div>}
        {tab === 'eod' && (eod || []).map((s, i) => <SignalRow key={i} s={s} selected={selKey === keyOf(s)} onSelect={onSelect} />)}
        {tab === 'eod' && (eod || []).length === 0 && <div className="rp-empty">No EOD signals</div>}
      </div>

      {tab === 'watch' &&
        <div className="rp-foot">
          <span className="rp-foot-lbl mono">TradingView import</span>
          <button className="rp-copy" onClick={copyWL}>{copied ? 'Copied!' : `Copy ${items.length}`}</button>
        </div>}
    </div>
  );
}

/* ═══════════════════════ CHART WORKSPACE (Chart tab) ═══════════════════════ */
function ChartWorkspace({ selected, onSelect, watchlist, intraday, fakeouts, eod }) {
  return (
    <div className="ws">
      <div className="ws-chart"><window.ChartPanel item={selected} /></div>
      <div className="ws-side">
        <RightPanel selected={selected} onSelect={onSelect}
          watchlist={watchlist} intraday={intraday} fakeouts={fakeouts} eod={eod} />
      </div>
    </div>
  );
}

/* ═══════════════════════ BACKTEST ═══════════════════════ */
function BacktestView({ backtest, onSelect }) {
  const [crit, setCrit] = React.useState('Prime');
  const [sort, setSort] = React.useState('pnl_pct');
  const [dir, setDir] = React.useState(-1);

  const rows = React.useMemo(() => backtest ? (backtest.rows || []) : [], [backtest]);
  const overall = React.useMemo(() => backtest ? backtest.overall_bt : null, [backtest]);

  const stats = React.useMemo(() => {
    if (crit === 'Prime') return overall;
    const typed = rows.map(r => r.by_type?.[crit]).filter(Boolean).filter(x => x.n > 0);
    if (!typed.length) return null;
    const n = typed.reduce((s, x) => s + x.n, 0);
    const nw = typed.reduce((s, x) => s + Math.round(x.n * x.wr / 100), 0);
    const pnl = typed.reduce((s, x) => s + (x.pnl_capital || 0), 0);
    const wins = typed.filter(x => x.avg_win != null).map(x => x.avg_win);
    const losses = typed.filter(x => x.avg_loss != null).map(x => x.avg_loss);
    return { n_trades: n, wr: n ? Math.round(nw / n * 1000) / 10 : 0, pnl_pct: Math.round(pnl * 10) / 10,
      avg_win: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0,
      avg_loss: losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : 0 };
  }, [crit, rows, overall]);

  const sorted = React.useMemo(() => {
    const arr = [...rows];
    arr.sort((a, b) => {
      if (sort === 'ticker') return dir * (a.ticker < b.ticker ? -1 : 1);
      let av = a[sort] ?? 0, bv = b[sort] ?? 0;
      if (crit !== 'Prime') {
        const km = { pnl_pct: 'pnl_capital', wr: 'wr', trades: 'n' };
        const ck = km[sort];
        if (ck) { av = a.by_type?.[crit]?.[ck] ?? -9999; bv = b.by_type?.[crit]?.[ck] ?? -9999; }
      }
      return dir * (av - bv);
    });
    return arr;
  }, [rows, sort, dir, crit]);

  if (!backtest) return <div className="page"><div className="loading">Loading backtest…</div></div>;
  if (backtest === false) return <div className="page"><div className="loading">Failed to load backtest.</div></div>;

  const opts = ['Prime', 'STR', 'RVOL', 'RSM', 'SMA50'];
  const getN = (r) => crit === 'Prime' ? r.trades : r.by_type?.[crit]?.n ?? null;
  const getWr = (r) => crit === 'Prime' ? r.wr : r.by_type?.[crit]?.wr ?? null;
  const getAW = (r) => crit === 'Prime' ? r.by_type?.Prime?.avg_win : r.by_type?.[crit]?.avg_win;
  const getAL = (r) => crit === 'Prime' ? r.by_type?.Prime?.avg_loss : r.by_type?.[crit]?.avg_loss;
  const getPnl = (r) => crit === 'Prime' ? r.pnl_pct : r.by_type?.[crit]?.pnl_capital ?? null;
  const onSort = (k, defDir = -1) => sort === k ? setDir(d => -d) : (setSort(k), setDir(defDir));
  const arrow = (k) => sort === k ? dir < 0 ? ' ▼' : ' ▲' : '';

  const SC = [
    { l: 'Total trades', v: stats ? fmt0(stats.n_trades) : '—', c: 'var(--navy)' },
    { l: 'Win rate', v: stats ? fmt1(stats.wr) + '%' : '—', c: stats && stats.wr >= 55 ? 'var(--green)' : 'var(--navy)' },
    { l: 'Total PnL', v: stats ? (stats.pnl_pct > 0 ? '+' : '') + fmt1(stats.pnl_pct) + '%' : '—', c: stats && stats.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)' },
    { l: 'Avg win', v: stats ? '+' + fmt1(stats.avg_win) + '%' : '—', c: 'var(--green)' },
    { l: 'Avg loss', v: stats ? fmt1(stats.avg_loss) + '%' : '—', c: 'var(--red)' },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div><h1 className="page-t">Backtest</h1><p className="page-sub">Per-symbol breakout performance · as of {backtest.date}</p></div>
      </div>

      <div className="seg-bar">
        <span className="seg-lbl" style={{ marginLeft: 0 }}>Criteria</span>
        <div className="chips">
          {opts.map(c => <button key={c} className={`mpill c${c} ${crit === c ? 'on' : ''}`} onClick={() => setCrit(c)}>{c}</button>)}
        </div>
      </div>

      <div className="sc-row" style={{ gridTemplateColumns: 'repeat(5,1fr)' }}>
        {SC.map((s, i) => <div key={i} className="sc"><div className="sc-v mono" style={{ color: s.c }}>{s.v}</div><div className="sc-l">{s.l}</div></div>)}
      </div>

      <div className="mt-card">
        <table className="mt">
          <thead><tr>
            <th className="sortable" onClick={() => onSort('ticker', 1)}>Ticker{arrow('ticker')}</th>
            <th className="r sortable" onClick={() => onSort('trades')}>Trades{arrow('trades')}</th>
            <th className="r sortable" onClick={() => onSort('wr')}>Win %{arrow('wr')}</th>
            <th className="r">Avg Win</th><th className="r">Avg Loss</th>
            <th className="r sortable" onClick={() => onSort('pnl_pct')}>PnL{arrow('pnl_pct')}</th>
            <th className="r sortable" onClick={() => onSort('rsm')}>RSM{arrow('rsm')}</th>
          </tr></thead>
          <tbody>
            {sorted.length === 0 && <tr><td colSpan="7" style={{ textAlign: 'center', color: 'var(--mut3)', padding: 22 }}>No backtest data — run EOD scan first</td></tr>}
            {sorted.map((r, i) => {
              const n = getN(r), wr = getWr(r), aw = getAW(r), al = getAL(r), pnl = getPnl(r);
              return (
                <tr key={i}>
                  <td><button className="mt-tk" onClick={() => onSelect && onSelect(r)}>{tickerText(r)}</button></td>
                  <td className="r mono dm">{n ?? '—'}</td>
                  <td className="r mono"><span className={wr >= 55 ? 'g' : 'dm'}>{n ? fmt1(wr) + '%' : '—'}</span></td>
                  <td className="r mono dm">{aw != null && aw !== 0 ? '+' + fmt2(aw) + '%' : '—'}</td>
                  <td className="r mono dm">{al != null && al !== 0 ? fmt2(al) + '%' : '—'}</td>
                  <td className="r mono"><span className={(pnl ?? 0) >= 0 ? 'g' : 'r'}>{pnl != null ? (pnl > 0 ? '+' : '') + fmt1(pnl) + '%' : '—'}</span></td>
                  <td className="r mono"><span className={r.rsm >= 80 ? 'b' : 'dm'}>{fmt0(r.rsm)}</span></td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════ PORTFOLIO ═══════════════════════ */
function PortfolioView({ portfolio, onSelect }) {
  if (!portfolio) return <div className="page"><div className="loading">Loading portfolio…</div></div>;
  if (portfolio === false) return <div className="page"><div className="loading">Failed to load portfolio.</div></div>;

  const { summary = {}, open = [], closed = [] } = portfolio;
  const sign = (v) => (v ?? 0) >= 0 ? '+' : '−';
  const pnlCls = (v) => (v ?? 0) >= 0 ? 'g' : 'r';
  const fmtDate = (iso) => { if (!iso) return '—'; try { return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); } catch { return iso; } };

  const invested = open.reduce((s, p) => s + (p.current_close ?? p.entry_price) * (p.shares_remaining || 0), 0);
  const cash = summary.available ?? 0;
  const equity = summary.equity ?? (cash + invested);
  const exposure = equity > 0 ? invested / equity * 100 : 0;
  const winners = open.filter(p => (p.unrealized_pnl ?? 0) > 0).length;
  const closedWins = closed.filter(c => (c.total_pnl ?? 0) > 0).length;

  const SC = [
    { l: 'Equity', v: `฿${fmt0(equity)}`, c: 'var(--navy)' },
    { l: 'Cash', v: `฿${fmt0(cash)}`, c: 'var(--navy)', s: 'available to trade' },
    { l: 'Realized', v: `${sign(summary.realized_pnl)}฿${fmt0(Math.abs(summary.realized_pnl || 0))}`, c: (summary.realized_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', s: 'closed P&L' },
    { l: 'Realized %', v: `${(summary.realized_pct ?? 0) >= 0 ? '+' : ''}${fmt2(summary.realized_pct)}%`, c: (summary.realized_pct ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', s: 'of capital' },
    { l: 'Exposure', v: `${fmt0(exposure)}%`, c: 'var(--navy)', s: `฿${fmt0(invested)} deployed` },
  ];

  const stageOf = (p) => p.tp2_hit ? 'tp2' : p.tp1_hit ? 'tp1' : p.be_activated ? 'be' : 'open';
  const stageTxt = { tp2: 'TP2', tp1: 'TP1', be: 'BE', open: 'OPEN' };

  return (
    <div className="page">
      <div className="page-head">
        <div><h1 className="page-t">Portfolio</h1><p className="page-sub">{open.length} open · {winners} in profit · ฿{fmt0(summary.available)} cash available</p></div>
        <div className="pf-winrate"><span className="k">Win rate</span><span className={`v mono ${(summary.win_rate ?? 0) >= 50 ? 'g' : 'r'}`}>{fmt0(summary.win_rate)}%</span></div>
      </div>

      <div className="sc-row" style={{ gridTemplateColumns: 'repeat(5,1fr)' }}>
        {SC.map((s, i) => <div key={i} className="sc"><div className="sc-v mono" style={{ color: s.c }}>{s.v ?? '—'}</div><div className="sc-l">{s.l}</div>{s.s && <div className="sc-s">{s.s}</div>}</div>)}
      </div>

      <div className="mt-card" style={{ marginBottom: 14 }}>
        <div className="card-head"><span className="card-head-t">Open Positions</span><span className="card-head-c">value ฿{fmt0(invested)}</span></div>
        <table className="mt" style={{ tableLayout: 'fixed' }}>
          {PF_COLS}
          <thead><tr>
            <th>Date</th><th>Ticker</th><th>Setup</th><th className="r">Shares</th>
            <th className="r">Entry</th><th className="r">Last</th><th className="r">P/L</th><th className="r">Status</th>
          </tr></thead>
          <tbody>
            {open.length === 0 && <tr><td colSpan="8" style={{ textAlign: 'center', color: 'var(--mut3)', padding: 22 }}>No open positions</td></tr>}
            {open.map((p, i) => {
              const up = (p.current_close ?? p.entry_price) >= p.entry_price;
              const upnl = p.unrealized_pnl ?? 0;
              const cost = (p.entry_price || 0) * (p.shares || 0);
              const upct = cost ? upnl / cost * 100 : 0;
              const stg = stageOf(p);
              return (
                <tr key={i}>
                  <td className="mono dm">{fmtDate(p.entry_date)}</td>
                  <td><button className="mt-tk" onClick={() => onSelect && onSelect(p)}>{tickerText(p)}</button></td>
                  <td>{p.criteria && <span className={`bg ${CC[p.criteria] || ''}`}>{p.criteria}</span>}</td>
                  <td className="r mono dm">{fmt0(p.shares_remaining)}</td>
                  <td className="r mono" style={{ color: 'var(--ink)' }}>{fmt2(p.entry_price)}</td>
                  <td className="r mono"><span className={up ? 'g' : 'r'}>{fmt2(p.current_close)}</span></td>
                  <td className="r mono"><span className={pnlCls(upnl)}>{sign(upnl)}฿{fmt0(Math.abs(upnl))} <span className="pf-pct">({upct >= 0 ? '+' : ''}{fmt1(upct)}%)</span></span></td>
                  <td className="r"><span className={`pf-stage ${stg}`}>{stageTxt[stg]}</span></td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-card">
        <div className="card-head"><span className="card-head-t">Closed</span><span className="card-head-c">{closedWins}/{closed.length} wins</span></div>
        <table className="mt" style={{ tableLayout: 'fixed' }}>
          {PF_COLS}
          <thead><tr>
            <th>Date</th><th>Ticker</th><th>Setup</th><th className="r">Shares</th>
            <th className="r">Entry</th><th className="r">Exit</th><th className="r">P/L</th><th className="r">Status</th>
          </tr></thead>
          <tbody>
            {closed.length === 0 && <tr><td colSpan="8" style={{ textAlign: 'center', color: 'var(--mut3)', padding: 22 }}>No closed trades yet</td></tr>}
            {closed.map((t, i) => {
              const win = (t.total_pnl ?? 0) > 0;
              const cCost = (t.entry_price || 0) * (t.shares || 0);
              const cPct = cCost ? (t.total_pnl || 0) / cCost * 100 : 0;
              return (
                <tr key={i}>
                  <td className="mono dm">{fmtDate(t.exit_date)}</td>
                  <td><button className="mt-tk" onClick={() => onSelect && onSelect(t)}>{tickerText(t)}</button></td>
                  <td>{t.criteria && <span className={`bg ${CC[t.criteria] || ''}`}>{t.criteria}</span>}</td>
                  <td className="r mono dm">{fmt0(t.shares)}</td>
                  <td className="r mono" style={{ color: 'var(--ink)' }}>{fmt2(t.entry_price)}</td>
                  <td className="r mono"><span className={t.exit_price >= t.entry_price ? 'g' : 'r'}>{fmt2(t.exit_price)}</span></td>
                  <td className="r mono"><span className={pnlCls(t.total_pnl)}>{sign(t.total_pnl)}฿{fmt0(Math.abs(t.total_pnl || 0))} <span className="pf-pct">({cPct >= 0 ? '+' : ''}{fmt1(cPct)}%)</span></span></td>
                  <td className="r"><span className={`pf-stage ${win ? 'tp1' : 'loss'}`}>{t.exit_reason ?? '—'}</span></td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════ JOBS (scheduler + runs + console) ═══════════════════════ */
function JobsView({ jobs, runs, running, onRun, onRunClick, onNotify, notifying, log }) {
  const [page, setPage] = React.useState(0);
  const PAGE = 5;
  const list = runs || [];
  const pageCount = Math.max(1, Math.ceil(list.length / PAGE));
  const shown = list.slice(page * PAGE, page * PAGE + PAGE);
  const stCls = (s) => ({ running: 'rn', completed: 'ok', failed: 'fl', stale: 'fl' })[s] || 'never';
  const stTxt = (s) => ({ running: 'RUNNING', completed: 'OK', failed: 'FAILED', stale: 'STALE' })[s] || 'NEVER';

  return (
    <div className="page">
      <div className="page-head">
        <div><h1 className="page-t">Jobs</h1><p className="page-sub">Scheduler status, manual runs & activity log</p></div>
        <button className="btn-dark" disabled={notifying?.discord} onClick={() => onNotify('discord')}>
          {notifying?.discord ? 'Sending…' : 'Discord Notify Test'}
        </button>
      </div>

      <div className="jc-row">
        {(jobs || []).map((j, i) =>
          <div key={i} className="jc">
            <div className="jc-top"><span className="jc-nm">{j.label}</span><span className={`st ${stCls(j.status)}`}>{stTxt(j.status)}</span></div>
            <div className="jc-meta">
              <div><span className="k">Last</span><span className="v mono">{j.last}</span></div>
              <div><span className="k">Next</span><span className="v mono">{j.next}</span></div>
              <div><span className="k">Duration</span><span className="v mono">{j.dur}</span></div>
            </div>
            <button className="jc-run" disabled={!!running[j.name]} onClick={() => onRun(j.name)}>{running[j.name] ? 'Running…' : 'Run now'}</button>
          </div>)}
      </div>

      <div className="jobs-2col">
        <div className="mt-card">
          <div className="card-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span className="card-head-t">Recent Runs</span>
              {pageCount > 1 &&
                <span className="mono" style={{ fontSize: 10.5, color: 'var(--mut)' }}>
                  <button className="tb-btn" style={{ padding: '1px 7px' }} disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>‹</button>
                  {' '}{page + 1}/{pageCount}{' '}
                  <button className="tb-btn" style={{ padding: '1px 7px' }} disabled={page >= pageCount - 1} onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))}>›</button>
                </span>}
            </div>
            <span className="card-head-c">{list.length} total</span>
          </div>
          <div className="rr-scroll">
            {shown.length === 0 && <div className="rp-empty">No runs yet</div>}
            {shown.map(r =>
              <div key={r.id} className="rr" onClick={() => onRunClick(r)}>
                <div className="rr-top">
                  <span className="rr-job">{String(r.job_name || '').replace(/_/g, ' ')}</span>
                  <span className={`st ${stCls(r.status)}`}>{stTxt(r.status)}</span>
                </div>
                <div className="rr-meta mono">{fmtDatetime(r.started_at)} · {r.duration_s != null ? r.duration_s.toFixed(1) + 's' : '—'} · {r.signals_found != null ? r.signals_found + ' sig' : '—'}</div>
              </div>)}
          </div>
        </div>

        <div className="mt-card">
          <div className="card-head"><span className="card-head-t">Console</span><span className="card-head-c">live</span></div>
          <div className="cons">
            {(log || []).length === 0 && <div className="cons-ln muted">No activity yet…</div>}
            {(log || []).map((l, i) => <div key={i} className={`cons-ln ${l.includes('ERROR') ? 'err' : ''}`}>{l}</div>)}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════ HELP DRAWER (FAQ) ═══════════════════════ */
function HelpDrawer({ onClose }) {
  return (
    <div className="hd-bg" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="hd">
        <div className="hd-head"><span className="hd-t">Help & Reference</span><button className="hd-x" onClick={onClose}>×</button></div>
        <div className="hd-body">
          <div className="hd-sec">
            <h3>Schedule</h3>
            <div className="hd-kv"><span>Intraday scan</span><span className="mono">every 15 min · 10:30–16:15</span></div>
            <div className="hd-kv"><span>Fakeout review</span><span className="mono">16:25</span></div>
            <div className="hd-kv"><span>EOD scan</span><span className="mono">16:45</span></div>
            <p className="hd-note">All times BKK (UTC+7), Mon–Fri. Scheduled runs send Discord notifications; manual “Run now” does not.</p>
          </div>
          <div className="hd-sec">
            <h3>Signal criteria</h3>
            <div className="hd-crit"><span className="bg P">Prime</span> Proj RVol ≥ 2.0× · RSM ≥ 80 · STR ≤ 4.0×</div>
            <div className="hd-crit"><span className="bg RV">RVOL</span> Volume strong, momentum below threshold</div>
            <div className="hd-crit"><span className="bg RS">RSM</span> Momentum strong, volume below threshold</div>
            <div className="hd-crit"><span className="bg ST">STR</span> Overextended (stretch &gt; 4.0×)</div>
            <div className="hd-crit"><span className="bg S5">SMA50</span> Baseline filter, no high-conviction trigger</div>
          </div>
          <div className="hd-sec">
            <h3>Money management</h3>
            <div className="hd-kv"><span>Stop loss</span><span className="mono">1 × ATR below entry</span></div>
            <div className="hd-kv"><span>TP1</span><span className="mono">+2 ATR · sell 30%</span></div>
            <div className="hd-kv"><span>TP2</span><span className="mono">+4 ATR · sell 30%</span></div>
            <div className="hd-kv"><span>Breakeven</span><span className="mono">after 3 bars → SL to entry</span></div>
            <div className="hd-kv"><span>Trail</span><span className="mono">exit rest below MA10</span></div>
            <div className="hd-kv"><span>Max risk</span><span className="mono">0.5% capital / position</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════ RUN DETAIL MODAL ═══════════════════════ */
function RunModal({ run, onClose }) {
  if (!run) return null;
  let result = {};
  try { result = run.result_json ? JSON.parse(run.result_json) : {}; } catch {}
  const stdout = String(result.stdout || '').trim();
  const stderr = String(result.stderr || '').trim();
  const logText = stdout || stderr ? `STDOUT:\n${stdout || '(empty)'}\n\nSTDERR:\n${stderr || '(empty)'}` : '';
  const stCls = (s) => ({ running: 'rn', completed: 'ok', failed: 'fl' })[s] || 'never';

  return (
    <div className="modal-bg" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <div className="modal-h">
          <span className="nm">{String(run.job_name || '').replace(/_/g, ' ')}</span>
          <button className="modal-x" onClick={onClose}>×</button>
        </div>
        <div className="modal-b">
          <div className="kv"><span className="k">Status</span><span className={`st ${stCls(run.status)}`}>{run.status}</span></div>
          <div className="kv"><span className="k">Started</span><span className="v mono">{fmtDatetime(run.started_at)}</span></div>
          <div className="kv"><span className="k">Finished</span><span className="v mono">{run.finished_at ? fmtDatetime(run.finished_at) : '—'}</span></div>
          <div className="kv"><span className="k">Duration</span><span className="v mono">{run.duration_s != null ? run.duration_s.toFixed(1) + 's' : '—'}</span></div>
          <div className="kv"><span className="k">Stocks scanned</span><span className="v mono">{run.stocks_scanned ?? '—'}</span></div>
          <div className="kv" style={{ borderBottom: 'none' }}><span className="k">Signals found</span><span className="v mono">{run.signals_found ?? '—'}</span></div>
          {logText && <><div className="term-lbl">Job output</div><pre className="term">{logText}</pre></>}
          {run.error && <><div className="term-lbl">Error</div><pre className="term err">{run.error}</pre></>}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  Topbar, NavRail, ChartWorkspace, RightPanel, BacktestView, PortfolioView, JobsView, HelpDrawer, RunModal,
});
