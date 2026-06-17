/* bs-app.jsx — app shell with real API integration. */
const { DashboardView, DashRail, BacktestView, WatchlistView, PortfolioView, ToolsView, FaqView, ChartView, RunModal } = window;
const { fmtDatetime, bkkDateIso, isMarketOpenOrLater } = window.BS;

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: '▦' },
  { id: 'backtest',  label: 'Backtest',  icon: '◷' },
  { id: 'watchlist',  label: 'Watchlist',  icon: '★' },
  { id: 'portfolio',  label: 'Portfolio',  icon: '฿' },
  { id: 'chart',      label: 'Chart',      icon: '∿' },
  { id: 'tools',     label: 'Tools',     icon: '⚙' },
  { id: 'faq',       label: 'FAQ',       icon: '?' },
];

const JOB_DEFS = [
  { name: 'intraday_scan', label: 'Intraday Scan',  next_key: 'intraday_scan' },
  { name: 'eod_scan',      label: 'EOD Scan',       next_key: 'eod_scan' },
  { name: 'review_scan',   label: 'Fakeout Review', next_key: 'review_scan' },
];

function buildJobs(lastRuns, nextRuns) {
  return JOB_DEFS.map(def => {
    const last = lastRuns?.[def.name];
    const nextIso = nextRuns?.[def.next_key];
    const status = last?.status || 'never';
    const isStale = status === 'running' && last?.started_at &&
      (Date.now() - new Date(last.started_at).getTime()) > 15 * 60 * 1000;
    return {
      name: def.name,
      label: def.label,
      status: isStale ? 'stale' : status,
      last: last?.started_at
        ? new Date(last.started_at).toLocaleTimeString('en-GB', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit' })
        : '—',
      next: nextIso
        ? new Date(nextIso).toLocaleTimeString('en-GB', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit' })
        : '—',
      dur: last?.duration_s != null ? last.duration_s.toFixed(1) + 's' : '—',
      error: last?.error || null,
    };
  });
}

function App() {
  const [tab, setTab] = React.useState(() => localStorage.getItem('bs_tab') || 'dashboard');
  const [schedulerRunning, setSchedulerRunning] = React.useState(false);
  const [recentRuns, setRecentRuns] = React.useState([]);
  const [nextRuns, setNextRuns] = React.useState({});
  const [lastRuns, setLastRuns] = React.useState({});
  const [signals, setSignals] = React.useState({ alerted_today: [], failed_today: [], alert_date: null });
  const [scanLatest, setScanLatest] = React.useState({ date: null, signals: [] });
  const [backtest, setBacktest] = React.useState(null);
  const [watchlist, setWatchlist] = React.useState(null);
  const [portfolio, setPortfolio] = React.useState(null);
  const [running, setRunning] = React.useState({});
  const [notifying, setNotifying] = React.useState({});
  const [log, setLog] = React.useState([]);
  const [toast, setToast] = React.useState(null);
  const [runModal, setRunModal] = React.useState(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [chartTicker, setChartTicker] = React.useState(null);
  const toastTimer   = React.useRef(null);
  const pollRef      = React.useRef(null);
  const logPollRef   = React.useRef(null);
  const logOffsetRef = React.useRef({});

  React.useEffect(() => { localStorage.setItem('bs_tab', tab); }, [tab]);

  /* ── Derived data with BKK date guards ──────────────────── */
  const intraday = React.useMemo(() => {
    const rows = signals?.alerted_today || [];
    if (!isMarketOpenOrLater()) return rows;
    return signals?.alert_date === bkkDateIso() ? rows : [];
  }, [signals]);

  const fakeouts = React.useMemo(() => {
    const rows = signals?.failed_today || [];
    if (!isMarketOpenOrLater()) return rows;
    return signals?.alert_date === bkkDateIso() ? rows : [];
  }, [signals]);

  const eod = scanLatest?.signals || [];
  const intradayDate = signals?.alert_date || '';
  const eodDate = scanLatest?.date || '';
  const jobs = React.useMemo(() => buildJobs(lastRuns, nextRuns), [lastRuns, nextRuns]);

  /* ── Helpers ─────────────────────────────────────────────── */
  const pushLog = (msg) => {
    const now = new Date().toLocaleTimeString('en-GB', {
      timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    setLog(l => [`[${now}] ${msg}`, ...l].slice(0, 50));
  };

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  };

  /* ── API loaders ─────────────────────────────────────────── */
  const loadSystem = async () => {
    try {
      const r = await fetch('/api/system');
      if (!r.ok) throw new Error(r.statusText);
      const d = await r.json();
      setSchedulerRunning(d.scheduler_running ?? false);
      setRecentRuns(d.recent_history || []);
      setNextRuns(d.next_runs || {});
      setLastRuns(d.last_runs || {});
      return true;
    } catch (e) {
      pushLog(`ERROR loadSystem: ${e.message}`);
      return false;
    }
  };

  const loadSignals = async () => {
    try {
      const r = await fetch('/api/signals');
      if (!r.ok) throw new Error(r.statusText);
      setSignals(await r.json());
      return true;
    } catch (e) {
      pushLog(`ERROR loadSignals: ${e.message}`);
      return false;
    }
  };

  const loadScanLatest = async () => {
    try {
      const r = await fetch('/api/scan/latest');
      if (!r.ok) throw new Error(r.statusText);
      setScanLatest(await r.json());
      return true;
    } catch (e) {
      pushLog(`ERROR loadScanLatest: ${e.message}`);
      return false;
    }
  };

  const loadBacktest = async () => {
    try {
      const r = await fetch('/api/backtest');
      if (!r.ok) throw new Error(r.statusText);
      setBacktest(await r.json());
      return true;
    } catch (e) {
      pushLog(`ERROR loadBacktest: ${e.message}`);
      setBacktest(false);
      return false;
    }
  };

  const loadWatchlist = async () => {
    try {
      const r = await fetch('/api/watchlist/detail');
      if (!r.ok) throw new Error(r.statusText);
      setWatchlist(await r.json());
      return true;
    } catch (e) {
      pushLog(`ERROR loadWatchlist: ${e.message}`);
      setWatchlist(false);
      return false;
    }
  };

  const loadPortfolio = async () => {
    try {
      const r = await fetch('/api/portfolio');
      if (!r.ok) throw new Error(r.statusText);
      setPortfolio(await r.json());
      return true;
    } catch (e) {
      pushLog(`ERROR loadPortfolio: ${e.message}`);
      setPortfolio(false);
      return false;
    }
  };

  const loadCore = () => Promise.all([loadSystem(), loadSignals(), loadScanLatest()])
    .then(results => results.every(Boolean));

  /* ── Initial load + 60s refresh ─────────────────────────── */
  React.useEffect(() => {
    loadCore();
    const id = setInterval(loadCore, 60000);
    return () => clearInterval(id);
  }, []);

  /* ── Poll system + stream job logs while any job is running ── */
  React.useEffect(() => {
    clearTimeout(pollRef.current);
    clearTimeout(logPollRef.current);

    const runningJobs = Object.entries(lastRuns)
      .filter(([, r]) => r.status === 'running')
      .map(([name]) => name);

    if (runningJobs.length === 0) return;

    pollRef.current = setTimeout(loadSystem, 5000);

    const pollLogs = async () => {
      for (const jobName of runningJobs) {
        const offset = logOffsetRef.current[jobName] || 0;
        try {
          const r = await fetch(`/api/jobs/log/${jobName}?offset=${offset}`);
          if (!r.ok) continue;
          const d = await r.json();
          if (d.lines && d.lines.length > 0) {
            d.lines.forEach(ln => { if (ln.trim()) pushLog(`[${jobName}] ${ln.trim()}`); });
            logOffsetRef.current[jobName] = d.total;
          }
        } catch {}
      }
      logPollRef.current = setTimeout(pollLogs, 3000);
    };
    logPollRef.current = setTimeout(pollLogs, 2000);

    return () => { clearTimeout(pollRef.current); clearTimeout(logPollRef.current); };
  }, [lastRuns]);

  /* ── Lazy load backtest / watchlist on tab switch ────────── */
  React.useEffect(() => {
    if (tab === 'backtest'  && backtest   === null) loadBacktest();
    if (tab === 'watchlist' && watchlist  === null) loadWatchlist();
    if (tab === 'portfolio' && portfolio  === null) loadPortfolio();
  }, [tab]);

  /* ── Actions ─────────────────────────────────────────────── */
  const openChart = (item) => { setChartTicker(item); setTab('chart'); };

  const runJob = async (name) => {
    if (running[name]) return;
    setRunning(r => ({ ...r, [name]: true }));
    logOffsetRef.current[name] = 0;
    const label = JOB_DEFS.find(d => d.name === name)?.label || name;
    pushLog(`Triggering job: ${name}…`);
    try {
      const r = await fetch(`/api/jobs/run/${name}`, { method: 'POST' });
      const d = await r.json();
      if (r.ok) {
        showToast(`${label} triggered`);
        pushLog(`${name} triggered OK`);
        setTimeout(loadSystem, 2000);
      } else {
        showToast(d.detail || 'Job failed', false);
        pushLog(`ERROR ${name}: ${d.detail || r.statusText}`);
      }
    } catch (e) {
      showToast('Network error', false);
      pushLog(`ERROR ${name}: ${e.message}`);
    } finally {
      setRunning(r => ({ ...r, [name]: false }));
    }
  };

  const testNotify = async (channel) => {
    setNotifying(n => ({ ...n, [channel]: true }));
    pushLog(`Sending ${channel.toUpperCase()} test notification…`);
    try {
      const r = await fetch(`/api/notify/test/${channel}`, { method: 'POST' });
      const d = await r.json();
      if (r.ok) {
        showToast(`${channel.toUpperCase()} notification sent`);
        pushLog(`${channel.toUpperCase()} notification sent OK`);
      } else {
        showToast(d.detail || 'Notify failed', false);
        pushLog(`ERROR notify: ${d.detail || r.statusText}`);
      }
    } catch (e) {
      showToast('Network error', false);
      pushLog(`ERROR notify: ${e.message}`);
    } finally {
      setNotifying(n => ({ ...n, [channel]: false }));
    }
  };

  const refreshAll = async () => {
    if (refreshing) return;
    setRefreshing(true);
    pushLog('Refreshing all data…');
    try {
      const results = [await loadCore()];
      if (tab === 'backtest')  results.push(await loadBacktest());
      if (tab === 'portfolio') results.push(await loadPortfolio());
      if (tab === 'watchlist') results.push(await loadWatchlist());
      const ok = results.every(Boolean);
      showToast(ok ? 'Data refreshed' : 'Some data failed to load', ok);
      pushLog(ok ? 'Refresh complete' : 'Refresh partial — check log');
    } catch (e) {
      showToast('Refresh failed', false);
      pushLog(`ERROR refresh: ${e.message}`);
    } finally {
      setRefreshing(false);
    }
  };

  /* ── Render ──────────────────────────────────────────────── */
  const isDash  = tab === 'dashboard';
  const isChart = tab === 'chart';

  return (
    <div className="app">
      <div className="topbar">
        <div className="logo"><span className="mark">↑</span> Breakout Signal</div>
        <span className="set">Thai SET Market</span>
        <div className="top-r">
          <span className={`dot ${schedulerRunning ? '' : 'off'}`}></span>
          <span>{schedulerRunning ? 'Scheduler running' : 'Scheduler stopped'}</span>
          <span className="sep">·</span>
          <span className="mono">{bkkDateIso()}</span>
          <button className={`ref-btn ${refreshing ? 'spin' : ''}`} onClick={refreshAll}>
            <span className="ri">↻</span> Refresh
          </button>
        </div>
      </div>

      <div className="main-row">
        <div className="sidebar">
          <div className="nav-sec">Navigation</div>
          {NAV.map(n =>
            <div key={n.id} className={`nav-i ${tab === n.id ? 'act' : ''}`} onClick={() => setTab(n.id)}>
              <span className="nav-ic">{n.icon}</span><span>{n.label}</span>
            </div>
          )}
          <div className="nav-spacer"></div>
          <div className="nav-foot">
            <div className="lbl">Job Status</div>
            {jobs.map((j, i) => {
              const dc = j.status === 'running' ? 'rn'
                : (j.status === 'failed' || j.status === 'stale') ? 'fl'
                : j.status === 'completed' ? 'ok' : 'ny';
              return (
                <div key={i} className="mini-job">
                  <span className={`mini-dot ${dc}`}></span>
                  <span className="mini-lbl">{j.label}</span>
                  <span className="mini-t mono">{j.last}</span>
                </div>
              );
            })}
          </div>
        </div>

        {isChart ?
          <div className="content" style={{ overflow: 'hidden' }}>
            <ChartView ticker={chartTicker} />
          </div>
        : isDash ?
          <div className="content dash">
            <DashboardView
              openChart={openChart}
              intraday={intraday}
              fakeouts={fakeouts}
              eod={eod}
              intradayDate={intradayDate}
              eodDate={eodDate}
            />
            <DashRail
              jobs={jobs}
              runs={recentRuns}
              running={running}
              onRun={runJob}
              onRunClick={setRunModal}
            />
          </div>
        :
          <div className="content">
            {tab === 'backtest'  && <BacktestView  openChart={openChart} backtest={backtest} />}
            {tab === 'watchlist' && <WatchlistView openChart={openChart} watchlist={watchlist} />}
            {tab === 'portfolio' && <PortfolioView openChart={openChart} portfolio={portfolio} />}
            {tab === 'tools'     && <ToolsView jobs={jobs} running={running} onRun={runJob} log={log} onNotify={testNotify} notifying={notifying} />}
            {tab === 'faq'       && <FaqView />}
          </div>
        }
      </div>

      {toast && <div className={`toast ${toast.ok ? 'ok' : 'err'}`}>{toast.msg}</div>}
      <RunModal run={runModal} onClose={() => setRunModal(null)} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
