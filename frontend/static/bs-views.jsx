/* bs-views.jsx — all tab view components. Data passed as props; helpers from window.BS. */
const { fmt0, fmt1, fmt2, fmtDatetime, kindLabel, tickerText, tickerFull, CC } = window.BS;

const RVolCell = ({ v }) => v != null ? <span className={v >= 2 ? 'g' : 'r'}>{fmt1(v)}×</span> : <span className="dm">—</span>;
const RsmCell  = ({ v }) => v != null ? <span className={v >= 80 ? 'g' : 'r'}>{fmt0(v)}</span> : <span className="dm">—</span>;
const StrCell  = ({ v }) => v != null ? <span className={v <= 4 ? 'g' : 'r'}>{fmt1(v)}×</span> : <span className="dm">—</span>;

const fmtDay = (d) => {
  if (!d) return '';
  try {
    const [, m, day] = d.split('-');
    if (!m || !day) return d;
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${parseInt(day)} ${months[parseInt(m) - 1]}`;
  } catch { return d; }
};

/* ═══════════════════════ DASHBOARD ═══════════════════════ */
function DashboardView({ openChart, intraday, fakeouts, eod, intradayDate, eodDate }) {
  const sharedThead = (lastCol) => (
    <thead><tr>
      <th style={{ textAlign: 'center' }}>Ticker</th>
      <th style={{ width: 275, textAlign: 'center' }}>Sector</th>
      <th className="r">Level</th>
      <th className="r" style={{ width: 161 }}>Price</th>
      <th style={{ textAlign: 'center' }}>Type</th>
      <th className="c" style={{ width: 177 }}>Criteria</th>
      <th className="r">RVol</th>
      <th className="r">RSM</th>
      <th className="r">{lastCol}</th>
    </tr></thead>
  );

  return (
    <div className="col-main">
      {/* Intraday alerts */}
      <div>
        <div className="sec-h">Intraday Alerts <span className="dim">{fmtDay(intradayDate)}</span></div>
        <div className="card">
          <table className="t">
            {sharedThead('STR')}
            <tbody>
              {(intraday || []).length === 0 && <tr><td colSpan="9" className="empty">No intraday alerts</td></tr>}
              {(intraday || []).map((s, i) =>
                <tr key={i}>
                  <td><button className="tk" onClick={() => openChart(s)}>{tickerText(s)}</button></td>
                  <td className="dm">{s.sector}</td>
                  <td className="num">฿{fmt2(s.level)}</td>
                  <td className="num">฿{fmt2(s.close)}</td>
                  <td className="dm">{kindLabel(s)}</td>
                  <td className="c"><span className={`bg ${CC[s.criteria] || ''}`}>{s.criteria}</span></td>
                  <td className="num"><RVolCell v={s.proj_rvol} /></td>
                  <td className="num"><RsmCell v={s.rsm} /></td>
                  <td className="num"><StrCell v={s.stretch} /></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Fakeout review */}
      <div>
        <div className="sec-h">Fakeout Review <span className="dim">{fmtDay(intradayDate)}</span></div>
        <div className="card">
          <table className="t">
            {sharedThead('Detected at')}
            <tbody>
              {(fakeouts || []).length === 0 && <tr><td colSpan="9" className="empty">No fakeouts</td></tr>}
              {(fakeouts || []).map((f, i) =>
                <tr key={i} className="fk">
                  <td><button className="tk red" onClick={() => openChart(f)}>{tickerText(f)}</button></td>
                  <td className="dm">—</td>
                  <td className="num">฿{fmt2(f.level)}</td>
                  <td className="num">฿{fmt2(f.close)}</td>
                  <td className="dm">{kindLabel(f)}</td>
                  <td className="c dm">—</td>
                  <td className="num dm">—</td>
                  <td className="num dm">—</td>
                  <td className="dm" style={{ fontSize: 10.5 }}>{fmtDatetime(f.failed_at)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* EOD breakout signals */}
      <div>
        <div className="sec-h">EOD Breakout Signals <span className="dim">{fmtDay(eodDate)}</span></div>
        <div className="card">
          <table className="t">
            {sharedThead('STR')}
            <tbody>
              {(eod || []).length === 0 && <tr><td colSpan="9" className="empty">No EOD signals</td></tr>}
              {(eod || []).map((s, i) =>
                <tr key={i}>
                  <td><button className="tk" onClick={() => openChart(s)}>{tickerText(s)}</button></td>
                  <td className="dm">{s.sector}</td>
                  <td className="num b">฿{fmt2(s.bp)}</td>
                  <td className="num">฿{fmt2(s.close)}</td>
                  <td className="dm">{kindLabel(s)}</td>
                  <td className="c"><span className={`bg ${CC[s.filter_type] || ''}`}>{s.filter_type}</span></td>
                  <td className="num"><RVolCell v={s.rvol} /></td>
                  <td className="num"><RsmCell v={s.rsm} /></td>
                  <td className="num"><StrCell v={s.stretch} /></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* right rail: job cards + recent runs */
function DashRail({ jobs, runs, running, onRun, onRunClick }) {
  const stCls = (s) => ({ running: 'rn', completed: 'ok', failed: 'fl', stale: 'fl' })[s] || 'never';
  const stTxt = (s) => ({ running: 'RUNNING', completed: 'OK', failed: 'FAILED', stale: 'STALE' })[s] || 'NEVER';
  return (
    <div className="rail">
      {jobs.map((j, i) =>
        <div key={i} className="jcard">
          <div className="jcard-top">
            <span className="jcard-nm">{j.label}</span>
            <span className={`st ${stCls(j.status)}`}>{stTxt(j.status)}</span>
          </div>
          <div className="jcard-meta">
            <span>Last {j.last}</span><span>Next {j.next}</span>
            <span className="jcard-dur mono">{j.dur}</span>
          </div>
        </div>
      )}
      <div className="rail-h">
        <span className="t">Recent Runs</span><span className="c">{(runs || []).length} total</span>
      </div>
      <div>
        {(runs || []).map((r) =>
          <div key={r.id} className="run-row" onClick={() => onRunClick(r)}>
            <div className="run-row-top">
              <span className="run-job">{String(r.job_name || '').replace(/_/g, ' ')}</span>
              <span className={`st ${stCls(r.status)}`}>{stTxt(r.status)}</span>
            </div>
            <div className="run-meta">
              <span className="mono">{fmtDatetime(r.started_at)}</span>
              <span>·</span>
              <span>{r.duration_s != null ? r.duration_s.toFixed(1) + 's' : '—'}</span>
              <span>·</span>
              <span>{r.signals_found != null ? r.signals_found + ' sig' : '—'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════ BACKTEST ═══════════════════════ */
function BacktestView({ openChart, backtest }) {
  const [mode, setMode] = React.useState('daily');
  const [crit, setCrit] = React.useState('Prime');
  const [sort, setSort] = React.useState('pnl_pct');
  const [dir, setDir] = React.useState(-1);

  /* All hooks before any conditional return */
  const rows = React.useMemo(
    () => !backtest ? [] : mode === 'intraday' ? backtest.intraday_bt?.rows || [] : backtest.rows || [],
    [backtest, mode]
  );
  const overall = React.useMemo(
    () => !backtest ? null : mode === 'intraday' ? backtest.intraday_bt?.overall_bt : backtest.overall_bt,
    [backtest, mode]
  );

  const stats = React.useMemo(() => {
    if (crit === 'Prime') return overall;
    const typed = rows.map(r => r.by_type?.[crit]).filter(Boolean).filter(x => x.n > 0);
    if (!typed.length) return null;
    const n = typed.reduce((s, x) => s + x.n, 0);
    const nw = typed.reduce((s, x) => s + Math.round(x.n * x.wr / 100), 0);
    const pnl = typed.reduce((s, x) => s + (x.pnl_capital || 0), 0);
    const wins = typed.filter(x => x.avg_win != null).map(x => x.avg_win);
    const losses = typed.filter(x => x.avg_loss != null).map(x => x.avg_loss);
    return {
      n_trades: n,
      wr: n ? Math.round(nw / n * 1000) / 10 : 0,
      pnl_pct: Math.round(pnl * 10) / 10,
      avg_win: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0,
      avg_loss: losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : 0,
    };
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

  if (!backtest) return <div className="pad"><div className="loading">Loading backtest data…</div></div>;

  const opts = mode === 'intraday' ? ['Prime', 'RVOL'] : ['Prime', 'STR', 'RVOL', 'RSM', 'SMA50'];
  const note = mode === 'intraday' ? backtest.intraday_bt?.overall_bt?.note : '';

  const getN   = (r) => crit === 'Prime' ? r.trades : r.by_type?.[crit]?.n ?? null;
  const getWr  = (r) => crit === 'Prime' ? r.wr : r.by_type?.[crit]?.wr ?? null;
  const getAW  = (r) => crit === 'Prime' ? r.by_type?.Prime?.avg_win : r.by_type?.[crit]?.avg_win;
  const getAL  = (r) => crit === 'Prime' ? r.by_type?.Prime?.avg_loss : r.by_type?.[crit]?.avg_loss;
  const getPnl = (r) => crit === 'Prime' ? r.pnl_pct : r.by_type?.[crit]?.pnl_capital ?? null;

  const onSort = (k, defDir = -1) => sort === k ? setDir(d => -d) : (setSort(k), setDir(defDir));
  const arrow  = (k) => sort === k ? dir < 0 ? ' ▼' : ' ▲' : '';

  return (
    <div className="pad">
      <div className="bt-bar">
        <span className="bt-lbl">Mode:</span>
        <button className={`pill ${mode === 'daily' ? 'on-d' : ''}`} onClick={() => { setMode('daily'); setCrit('Prime'); }}>Daily</button>
        <button className={`pill ${mode === 'intraday' ? 'on-i' : ''}`} onClick={() => { setMode('intraday'); setCrit('Prime'); }}>Intraday</button>
        <span className="bt-lbl" style={{ marginLeft: 8 }}>Criteria:</span>
        {opts.map(c =>
          <button key={c} className={`pill c${c} ${crit === c ? 'on' : ''}`} onClick={() => setCrit(c)}>{c}</button>
        )}
        <span className="bt-asof">as of {backtest.date}</span>
      </div>

      {note && <div className="bt-note">{note}</div>}

      <div className="stats">
        <div className="stat"><div className="stat-v" style={{ color: 'var(--navy)' }}>{stats ? stats.n_trades : '—'}</div><div className="stat-l">Total trades</div></div>
        <div className="stat"><div className="stat-v" style={{ color: stats && stats.wr >= 55 ? 'var(--green)' : 'var(--navy)' }}>{stats ? fmt1(stats.wr) + '%' : '—'}</div><div className="stat-l">Win rate</div></div>
        <div className="stat"><div className="stat-v" style={{ color: stats && stats.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>{stats ? (stats.pnl_pct > 0 ? '+' : '') + fmt1(stats.pnl_pct) + '%' : '—'}</div><div className="stat-l">Total PnL</div></div>
        <div className="stat"><div className="stat-v" style={{ color: 'var(--green)' }}>{stats ? '+' + fmt1(stats.avg_win) + '%' : '—'}</div><div className="stat-l">Avg win</div></div>
        <div className="stat"><div className="stat-v" style={{ color: 'var(--red)' }}>{stats ? fmt1(stats.avg_loss) + '%' : '—'}</div><div className="stat-l">Avg loss</div></div>
      </div>

      <div className="card">
        <table className="t">
          <thead><tr>
            <th className="sort" onClick={() => onSort('ticker', 1)}>Ticker{arrow('ticker')}</th>
            <th className="r sort" onClick={() => onSort('trades')}>Trades{arrow('trades')}</th>
            <th className="r sort" onClick={() => onSort('wr')}>WR%{arrow('wr')}</th>
            <th className="r">Avg Win</th>
            <th className="r">Avg Loss</th>
            <th className="r sort" onClick={() => onSort('pnl_pct')}>PnL%{arrow('pnl_pct')}</th>
            <th className="r sort" onClick={() => onSort('rsm')}>RSM{arrow('rsm')}</th>
          </tr></thead>
          <tbody>
            {sorted.length === 0 && <tr><td colSpan="7" className="empty">No backtest data — run EOD scan first</td></tr>}
            {sorted.map((r, i) => {
              const n = getN(r), wr = getWr(r), aw = getAW(r), al = getAL(r), pnl = getPnl(r);
              return (
                <tr key={i}>
                  <td><button className="tk" onClick={() => openChart(r)}>{tickerText(r)}</button></td>
                  <td className="num">{n ?? '—'}</td>
                  <td className="num"><span className={wr >= 55 ? 'g' : 'dm'}>{n ? fmt1(wr) + '%' : '—'}</span></td>
                  <td className="num g">{aw != null ? '+' + fmt2(aw) + '%' : '—'}</td>
                  <td className="num r">{al != null ? fmt2(al) + '%' : '—'}</td>
                  <td className="num"><span className={(pnl ?? 0) >= 0 ? 'g' : 'r'}>{pnl != null ? (pnl > 0 ? '+' : '') + fmt1(pnl) + '%' : '—'}</span></td>
                  <td className="num"><span className={r.rsm >= 80 ? 'b' : 'dm'}>{fmt0(r.rsm)}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════ WATCHLIST ═══════════════════════ */
function WatchlistView({ openChart, watchlist }) {
  const [sort, setSort] = React.useState('pct_to_level');
  const [dir, setDir] = React.useState(1);
  const [copied, setCopied] = React.useState(false);

  /* All hooks before conditional return */
  const items = watchlist?.items || [];

  const groups = React.useMemo(() => {
    const order = ['> MA10', '> MA20', '> MA50', 'Other'];
    const map = {};
    order.forEach(k => map[k] = []);
    items.forEach(it => { (map[it.ma_group] || map['Other']).push(it); });
    return order.map(k => ({ key: k, items: map[k] })).filter(g => g.items.length);
  }, [items]);

  if (!watchlist) return <div className="pad"><div className="loading">Loading watchlist…</div></div>;

  const { copy_str = '', date } = watchlist;

  const sortGroup = (its) => {
    const arr = [...its];
    arr.sort((a, b) => {
      let av, bv;
      if (sort === 'pct_to_level') {
        const aL = a.levels?.[0]?.level, aC = a.close, bL = b.levels?.[0]?.level, bC = b.close;
        av = aL && aC ? (aL - aC) / aC * 100 : 9999;
        bv = bL && bC ? (bL - bC) / bC * 100 : 9999;
      } else if (sort === 'rsm')     { av = a.rsm ?? -1;       bv = b.rsm ?? -1; }
        else if (sort === 'rvol')    { av = a.rvol ?? -1;      bv = b.rvol ?? -1; }
        else if (sort === 'stretch') { av = a.stretch ?? 9999; bv = b.stretch ?? 9999; }
        else if (sort === 'close')   { av = a.close ?? 0;      bv = b.close ?? 0; }
        else if (sort === 'level')   { av = a.levels?.[0]?.level ?? 0; bv = b.levels?.[0]?.level ?? 0; }
        else return dir * ((a.ticker || '') < (b.ticker || '') ? -1 : 1);
      return dir * (av - bv);
    });
    return arr;
  };

  const onSort = (k, defDir = -1) => sort === k ? setDir(d => -d) : (setSort(k), setDir(defDir));
  const arrow = (k) => sort === k ? dir < 0 ? ' ▼' : ' ▲' : '';
  const tagCls = (k) => k.includes('10') ? 'g10' : k.includes('20') ? 'g20' : k.includes('50') ? 'g50' : 'go';

  const copy = () => {
    navigator.clipboard?.writeText(copy_str).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="pad">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 14 }}>
        <div className="sec-h" style={{ margin: 0 }}>Watching <span className="dim">{items.length} stocks</span></div>
        <span style={{ fontSize: 11, color: 'var(--mut2)' }}>as of {date}</span>
      </div>

      <div className="copy-box">
        <div className="copy-top">
          <span className="copy-lbl">TradingView Watchlist</span>
          <button className="copy-btn" onClick={copy}>{copied ? 'Copied!' : 'Copy all'}</button>
        </div>
        <div className="copy-str">{copy_str}</div>
      </div>

      {groups.map(grp =>
        <div key={grp.key} style={{ marginBottom: 20 }}>
          <div className="grp-h">
            <span className={`grp-tag ${tagCls(grp.key)}`}>{grp.key}</span>
            <span className="grp-c">{grp.items.length} stocks</span>
          </div>
          <div className="card">
            <table className="t">
              <thead><tr>
                <th className="sort" onClick={() => onSort('ticker', 1)} style={{ width: 144 }}>Ticker{arrow('ticker')}</th>
                <th className="r sort" onClick={() => onSort('level')} style={{ width: 162 }}>Level{arrow('level')}</th>
                <th className="r sort" onClick={() => onSort('close')} style={{ width: 162 }}>Close{arrow('close')}</th>
                <th className="r sort" onClick={() => onSort('pct_to_level', 1)}>% to Level{arrow('pct_to_level')}</th>
                <th className="r sort" onClick={() => onSort('rvol')}>RVol{arrow('rvol')}</th>
                <th className="r sort" onClick={() => onSort('rsm')}>RSM{arrow('rsm')}</th>
                <th className="r sort" onClick={() => onSort('stretch', 1)} style={{ width: 120 }}>STR{arrow('stretch')}</th>
              </tr></thead>
              <tbody>
                {sortGroup(grp.items).map((s, i) => {
                  const lvl = s.levels?.[0]?.level;
                  const pct = lvl && s.close ? (lvl - s.close) / s.close * 100 : null;
                  return (
                    <tr key={i} className={s.broke ? 'broke' : ''}>
                      <td><button className={`tk ${s.broke ? 'green' : ''}`} onClick={() => openChart(s)}>{tickerText(s)}</button></td>
                      <td className="num">฿{fmt2(lvl)}</td>
                      <td className="num" style={s.broke ? { color: 'var(--green)', fontWeight: 700 } : {}}>฿{fmt2(s.close)}</td>
                      <td className="num"><span className={pct != null && pct <= 3 ? 'g' : 'dm'}>{pct != null ? fmt1(pct) + '%' : '—'}</span></td>
                      <td className="num"><span className={s.rvol >= 2 ? 'g' : ''}>{s.rvol ? fmt1(s.rvol) + '×' : '—'}</span></td>
                      <td className="num"><span className={s.rsm >= 80 ? 'g' : ''}>{s.rsm ? fmt0(s.rsm) : '—'}</span></td>
                      <td className="num"><span className={(s.stretch || 0) > 4 ? 'r' : 'dm'}>{s.stretch ? fmt1(s.stretch) + '×' : '—'}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════ TOOLS ═══════════════════════ */
function ToolsView({ jobs, running, onRun, log, onNotify, notifying }) {
  const stCls = (s) => ({ running: 'rn', completed: 'ok', failed: 'fl', stale: 'fl' })[s] || 'never';
  const stTxt = (s) => ({ running: 'RUNNING', completed: 'OK', failed: 'FAILED', stale: 'STALE' })[s] || 'NEVER';
  return (
    <div className="pad">
      <div className="tools-btns">
        <button className="btn-dark" disabled={notifying.discord} onClick={() => onNotify('discord')}>
          {notifying.discord ? 'Sending Discord…' : 'Discord Notify Test'}
        </button>
      </div>

      <div className="sec-h">Scheduled Jobs</div>
      <div className="jobs-grid">
        {jobs.map((j, i) =>
          <div key={i} className="card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--navy)' }}>{j.label}</span>
              <span className={`st ${stCls(j.status)}`}>{stTxt(j.status)}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--mut)', lineHeight: 1.9 }}>
              <div>Last: <span style={{ color: 'var(--ink)' }} className="mono">{j.last}</span></div>
              <div>Duration: <span style={{ color: 'var(--ink)' }} className="mono">{j.dur}</span></div>
              <div>Next: <span style={{ color: 'var(--ink)' }} className="mono">{j.next}</span></div>
            </div>
            <button className="jcard-run" disabled={!!running[j.name]} onClick={() => onRun(j.name)}>
              {running[j.name] ? 'Running…' : 'Run now'}
            </button>
          </div>
        )}
      </div>

      <div className="sec-h">Console</div>
      <div className="console">
        {log.length === 0 && <div className="ln muted">No activity yet…</div>}
        {log.map((l, i) =>
          <div key={i} className={`ln ${l.includes('ERROR') ? 'err' : ''}`}>{l}</div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════ FAQ ═══════════════════════ */
function FaqView() {
  return (
    <div className="pad">
      <div className="sec-h">Frequently Asked Questions</div>
      <div className="faq-grid">
        <div className="faq-card">
          <h3 className="faq-q">How often do scripts run?</h3>
          <div className="faq-b">
            <div className="sub">Market session</div>
            <div>10:30–12:30, 14:00–16:15 — Intraday scan every 15 min</div>
            <div className="sub">End of day</div>
            <div>16:25 — Fakeout review</div>
            <div>16:45 — EOD scan</div>
            <div className="ghost" style={{ marginTop: 6 }}>All times BKK (UTC+7), Mon–Fri</div>
          </div>
        </div>
        <div className="faq-card">
          <h3 className="faq-q">What happens when I click Run now?</h3>
          <div className="faq-b">
            <div>It triggers the selected job immediately in the background.</div>
            <div style={{ marginTop: 6 }}>Manual web-triggered runs do <strong>not</strong> send notification messages.</div>
            <div style={{ marginTop: 6 }}>Scheduled Railway runs <strong>do</strong> send notifications.</div>
          </div>
        </div>
        <div className="faq-card">
          <h3 className="faq-q">Signal criteria labels</h3>
          <div className="faq-b" style={{ lineHeight: 1.9 }}>
            <div><span className="bg P">Prime</span> &nbsp;Proj RVol ≥ 2.0× and RSM ≥ 80 and STR ≤ 4.0×</div>
            <div><span className="bg RV">RVOL</span> &nbsp;Volume strong but momentum below threshold</div>
            <div><span className="bg RS">RSM</span> &nbsp;Momentum strong but projected volume below threshold</div>
            <div><span className="bg ST">STR</span> &nbsp;Overextended (stretch &gt; 4.0×)</div>
            <div><span className="bg S5">SMA50</span> &nbsp;Baseline filter, no high-conviction trigger</div>
          </div>
        </div>
        <div className="faq-card">
          <h3 className="faq-q">How to read dashboard tables</h3>
          <div className="faq-b">
            <div><strong>Intraday Alerts</strong> — accumulates unique triggers during the day.</div>
            <div style={{ marginTop: 5 }}><strong>EOD Breakout Signals</strong> — latest end-of-day shortlist.</div>
            <div style={{ marginTop: 5 }}><strong>Fakeout Review</strong> — symbols that failed after trigger and dropped below level.</div>
            <div style={{ marginTop: 5 }}><strong>Recent Runs</strong> — click any row to inspect terminal output and errors.</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-h"><span className="card-t">Money Management Plan</span></div>
        <table className="t">
          <thead><tr><th style={{ width: 140 }}>Rule</th><th>Behavior</th></tr></thead>
          <tbody>
            <tr><td style={{ fontWeight: 700 }}>SL</td><td className="dm">1 × ATR below entry</td></tr>
            <tr><td style={{ fontWeight: 700 }}>TP1</td><td className="dm">Entry + 2 × ATR, sell 30%</td></tr>
            <tr><td style={{ fontWeight: 700 }}>TP2</td><td className="dm">Entry + 4 × ATR, sell 30%</td></tr>
            <tr><td style={{ fontWeight: 700 }}>Breakeven</td><td className="dm">After 3 bars, SL moves to entry</td></tr>
            <tr><td style={{ fontWeight: 700 }}>MA10 trail</td><td className="dm">Exit remaining when close drops below EMA10</td></tr>
            <tr><td style={{ fontWeight: 700 }}>Max risk</td><td className="dm">Default risk_pct = 0.5% of capital per position</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════ PORTFOLIO ═══════════════════════ */
function PortfolioView({ openChart, portfolio }) {
  if (!portfolio) return <div className="pad"><div className="loading">Loading…</div></div>;
  if (portfolio === false) return <div className="pad"><div className="empty">Failed to load portfolio.</div></div>;

  const { summary = {}, open = [], closed = [] } = portfolio;

  const pnlClass = (v) => (v ?? 0) >= 0 ? 'g' : 'r';
  const pnlSign  = (v) => (v ?? 0) >= 0 ? '+' : '';
  const exitCls  = (r) => r === 'SL' || r === 'Fakeout' ? 'r' : r === 'EMA10' || r === 'BE' ? 'dm' : 'g';

  return (
    <div className="pad">

      {/* ── KPI summary ── */}
      <div className="stats" style={{ gridTemplateColumns: 'repeat(6,1fr)', marginBottom: 20 }}>
        {[
          { l: 'Capital',       v: `฿${fmt0(summary.capital)}`,  s: null },
          { l: 'Available',     v: `฿${fmt0(summary.available)}`, s: `${summary.n_open ?? 0} open` },
          { l: 'Deployed',      v: `฿${fmt0(summary.deployed)}`,  s: null },
          { l: 'Realized P&L',  v: `${pnlSign(summary.realized_pnl)}฿${fmt0(summary.realized_pnl)}`,
            c: pnlClass(summary.realized_pnl), s: `${pnlSign(summary.realized_pct)}${fmt2(summary.realized_pct)}%` },
          { l: 'Unrealized P&L',v: `${pnlSign(summary.unrealized_pnl)}฿${fmt0(summary.unrealized_pnl)}`,
            c: pnlClass(summary.unrealized_pnl), s: `${pnlSign(summary.unrealized_pct)}${fmt2(summary.unrealized_pct)}%` },
          { l: 'Win Rate',      v: `${fmt1(summary.win_rate)}%`,
            c: (summary.win_rate ?? 0) >= 50 ? 'g' : 'r', s: `${summary.n_closed ?? 0} closed` },
        ].map(({ l, v, c, s }, i) => (
          <div key={i} className="stat">
            <div className={`stat-v ${c || ''}`} style={{ fontSize: 18 }}>{v ?? '—'}</div>
            <div className="stat-l">{l}</div>
            {s && <div style={{ fontSize: 10, color: 'var(--mut2)', marginTop: 2 }}>{s}</div>}
          </div>
        ))}
      </div>

      {/* ── Open positions ── */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <span className="card-t">Open Positions</span>
          <span className="card-d">{open.length} position{open.length !== 1 ? 's' : ''}</span>
        </div>
        <table className="t">
          <thead><tr>
            <th>Ticker</th>
            <th className="r">Entry</th>
            <th className="r">Close</th>
            <th className="r">Shares</th>
            <th className="r">SL</th>
            <th className="r">TP1</th>
            <th>Status</th>
            <th className="r">Unrealized P&L</th>
          </tr></thead>
          <tbody>
            {open.length === 0 && <tr><td colSpan="8" className="empty">No open positions</td></tr>}
            {open.map((p, i) => {
              const up = (p.current_close ?? p.entry_price) >= p.entry_price;
              const status = p.tp2_hit ? 'TP2 hit' : p.tp1_hit ? 'TP1 hit' : p.be_activated ? 'BE active' : '—';
              const upnl = p.unrealized_pnl ?? 0;
              return (
                <tr key={i}>
                  <td><button className="tk" onClick={() => openChart(p)}>{tickerText(p)}</button></td>
                  <td className="num">{fmt2(p.entry_price)}</td>
                  <td className={`num ${up ? 'g' : 'r'}`}>{fmt2(p.current_close)} {up ? '▲' : '▼'}</td>
                  <td className="num">{p.shares_remaining}</td>
                  <td className="num r">{fmt2(p.sl)}</td>
                  <td className="num g">{fmt2(p.tp1)}</td>
                  <td><span className="dm" style={{ fontSize: 11 }}>{status}</span></td>
                  <td className={`num ${pnlClass(upnl)}`}>{pnlSign(upnl)}฿{fmt0(upnl)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Closed trades ── */}
      <div className="card">
        <div className="card-h">
          <span className="card-t">Closed Trades</span>
          <span className="card-d">{closed.length} trade{closed.length !== 1 ? 's' : ''}</span>
        </div>
        <table className="t">
          <thead><tr>
            <th>Ticker</th>
            <th className="r">Entry</th>
            <th className="r">Exit</th>
            <th>Reason</th>
            <th className="r">Bars</th>
            <th className="r">Shares</th>
            <th className="r">P&L (฿)</th>
            <th className="r">Capital %</th>
          </tr></thead>
          <tbody>
            {closed.length === 0 && <tr><td colSpan="8" className="empty">No closed trades yet</td></tr>}
            {closed.map((t, i) => (
              <tr key={i} className={(t.total_pnl ?? 0) >= 0 ? '' : 'fk'}>
                <td><button className="tk" onClick={() => openChart(t)}>{tickerText(t)}</button></td>
                <td className="num">{fmt2(t.entry_price)}</td>
                <td className="num">{fmt2(t.exit_price)}</td>
                <td><span className={exitCls(t.exit_reason)} style={{ fontSize: 11, fontWeight: 600 }}>{t.exit_reason ?? '—'}</span></td>
                <td className="num">{t.bars_held ?? '—'}</td>
                <td className="num">{t.shares}</td>
                <td className={`num ${pnlClass(t.total_pnl)}`}>{pnlSign(t.total_pnl)}฿{fmt0(t.total_pnl)}</td>
                <td className={`num ${pnlClass(t.pnl_pct)}`}>{pnlSign(t.pnl_pct)}{fmt2(t.pnl_pct)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════ CHART ═══════════════════════ */
function ChartView({ ticker }) {
  const iframeRef = React.useRef(null);
  const loadedRef = React.useRef(false);
  const tkFull = ticker ? tickerFull(ticker) : null;

  React.useEffect(() => {
    if (!tkFull || !iframeRef.current || !loadedRef.current) return;
    try {
      iframeRef.current.contentWindow.postMessage({ type: 'goto', ticker: tkFull }, '*');
    } catch {}
  }, [tkFull]);

  const src = tkFull ? `/chart?ticker=${encodeURIComponent(tkFull)}` : '/chart';

  return (
    <div className="chart-wrap">
      <iframe
        ref={iframeRef}
        src={src}
        style={{ flex: 1, width: '100%', border: 'none', display: 'block' }}
        onLoad={() => { loadedRef.current = true; }}
      />
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
          {logText && <><div className="term-lbl">Job output (terminal)</div><pre className="term">{logText}</pre></>}
          {run.error && <><div className="term-lbl">Error</div><pre className="term err">{run.error}</pre></>}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  DashboardView, DashRail, BacktestView, WatchlistView, PortfolioView, ToolsView, FaqView, ChartView, RunModal
});
