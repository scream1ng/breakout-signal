/* frontend/static/app.js
 * Alpine.js data component for the Breakout Signal dashboard.
 * Auto-refreshes every 60 seconds.
 */

function app() {
  return {
    tab:              'dashboard',
    today:            new Date().toLocaleDateString('th-TH', { timeZone: 'Asia/Bangkok' }),
    schedulerRunning: false,
    recentRuns:       [],
    nextRuns:         {},
    lastRuns:         {},
    portfolio:        null,
    signals:          { watchlist: [], alerted_today: [], failed_today: [], alert_date: null, watchlist_date: null },
    scanLatest:       null,   // { date, n_signals, n_watching, signals: [] }
    backtest:         null,   // { date, overall_bt, rows }
    watchlistDetail:  null,   // { date, items, groups }
    btSort:           'pnl_pct',
    btSortDir:        -1,
    btCriteria:       'Prime',
    jobRunning:       {},
    toast:            { msg: '', ok: true },
    _refreshTimer:    null,

    // ── Lifecycle ──────────────────────────────────────────────────────────
    init() {
      this.loadSystem();
      this.loadScanLatest();
      this.loadSignals();
      this._refreshTimer = setInterval(() => this.refreshAll(), 60_000);
    },

    refreshAll() {
      this.loadSystem();
      this.loadScanLatest();
      if (this.tab === 'portfolio') this.loadPortfolio();
      if (this.tab === 'signals')   this.loadSignals();
      if (this.tab === 'backtest')  this.loadBacktest();
      if (this.tab === 'watchlist') this.loadWatchlistDetail();
    },

    // ── API calls ──────────────────────────────────────────────────────────
    async loadSystem() {
      try {
        const data = await fetch('/api/system').then(r => r.json());
        this.schedulerRunning = data.scheduler_running ?? false;
        this.recentRuns       = data.recent_history    ?? [];
        this.nextRuns         = data.next_runs         ?? {};
        this.lastRuns         = data.last_runs         ?? {};
      } catch (e) {
        console.error('loadSystem failed', e);
      }
    },

    async loadPortfolio() {
      try {
        this.portfolio = await fetch('/api/portfolio').then(r => r.json());
      } catch (e) {
        console.error('loadPortfolio failed', e);
      }
    },

    async loadSignals() {
      try {
        this.signals = await fetch('/api/signals').then(r => r.json());
      } catch (e) {
        console.error('loadSignals failed', e);
      }
    },

    async loadScanLatest() {
      try {
        this.scanLatest = await fetch('/api/scan/latest').then(r => r.json());
      } catch (e) {
        console.error('loadScanLatest failed', e);
      }
    },

    async loadBacktest() {
      try {
        this.backtest = await fetch('/api/backtest').then(r => r.json());
      } catch (e) {
        console.error('loadBacktest failed', e);
      }
    },

    async loadWatchlistDetail() {
      try {
        this.watchlistDetail = await fetch('/api/watchlist/detail').then(r => r.json());
      } catch (e) {
        console.error('loadWatchlistDetail failed', e);
      }
    },

    async runJob(jobName) {
      this.jobRunning = { ...this.jobRunning, [jobName]: true };
      try {
        const data = await fetch(`/api/jobs/run/${jobName}`, { method: 'POST' }).then(r => r.json());
        this.toast = { msg: `${data.job} triggered`, ok: true };
      } catch (e) {
        this.toast = { msg: `Failed to trigger ${jobName}`, ok: false };
      } finally {
        this.jobRunning = { ...this.jobRunning, [jobName]: false };
        setTimeout(() => { this.toast = { msg: '', ok: true }; }, 3000);
      }
      setTimeout(() => this.loadSystem(), 3000);
    },
    get btCriteriaStats() {
      if (!this.backtest?.rows?.length) return this.backtest?.overall_bt || null;
      const c = this.btCriteria;
      if (c === 'Prime') return this.backtest.overall_bt;
      const typed = this.backtest.rows.map(r => r.by_type?.[c]).filter(Boolean);
      if (!typed.length) return null;
      const nTrades = typed.reduce((s, x) => s + (x.n || 0), 0);
      const nWins   = typed.reduce((s, x) => s + Math.round((x.n || 0) * (x.wr || 0) / 100), 0);
      const pnl     = typed.reduce((s, x) => s + (x.pnl_capital || 0), 0);
      const wins    = typed.filter(x => x.avg_win  != null).map(x => x.avg_win);
      const losses  = typed.filter(x => x.avg_loss != null).map(x => x.avg_loss);
      return {
        n_trades: nTrades,
        wr:       nTrades > 0 ? Math.round(nWins / nTrades * 1000) / 10 : 0,
        pnl_pct:  Math.round(pnl * 10) / 10,
        avg_win:  wins.length   ? Math.round(wins.reduce((s,x)=>s+x,0)   / wins.length   * 100) / 100 : 0,
        avg_loss: losses.length ? Math.round(losses.reduce((s,x)=>s+x,0) / losses.length * 100) / 100 : 0,
      };
    },
    get btSortedRows() {
      if (!this.backtest?.rows) return [];
      const c   = this.btCriteria;
      const key = this.btSort;
      const dir = this.btSortDir;
      return [...this.backtest.rows].sort((a, b) => {
        let av = a[key] ?? 0, bv = b[key] ?? 0;
        if (c !== 'Prime') {
          const keyMap = { pnl_pct: 'pnl_capital', wr: 'wr', trades: 'n', rsm: null };
          const ck = keyMap[key];
          if (ck) { av = a.by_type?.[c]?.[ck] ?? -9999; bv = b.by_type?.[c]?.[ck] ?? -9999; }
        }
        return dir * (av - bv);
      });
    },

    get jobSummary() {
      const jobs = [
        { id: 'eod_scan',      label: 'EOD Scan',       nextKey: 'eod_scan' },
        { id: 'intraday_scan', label: 'Intraday Scan',  nextKey: 'intraday_scan' },
        { id: 'review_scan',   label: 'Fakeout Review', nextKey: 'review_scan' },
      ];
      return jobs.map(j => {
        const last     = this.lastRuns[j.id] ?? {};
        const status   = last.status ?? 'never';
        const dotClass = { completed: 'dot-green', failed: 'dot-red',
                           running: 'dot-yellow', never: 'dot-grey' }[status] ?? 'dot-grey';
        return {
          name:        j.id,
          label:       j.label,
          statusClass: dotClass,
          lastRun:     last.started_at ? this.fmtDatetime(last.started_at) : '—',
          duration:    last.duration_s != null ? last.duration_s.toFixed(1) + 's' : '—',
          nextRun:     this.nextRuns[j.nextKey] ? this.fmtDatetime(this.nextRuns[j.nextKey]) : '—',
          error:       last.error ?? null,
          running:     !!this.jobRunning[j.id],
        };
      });
    },

    // ── Formatting helpers ─────────────────────────────────────────────────
    fmtDatetime(iso) {
      if (!iso) return '—';
      try {
        return new Date(iso).toLocaleString('en-GB', {
          timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short',
          hour: '2-digit', minute: '2-digit',
        });
      } catch { return iso; }
    },

    fmtDate(iso) {
      if (!iso) return '—';
      try {
        return new Date(iso).toLocaleDateString('en-GB', {
          timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short',
        });
      } catch { return iso; }
    },

    fmt0(v) { return v != null ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—'; },
    fmt1(v) { return v != null ? Number(v).toFixed(1) : '—'; },
    fmt2(v) { return v != null ? Number(v).toFixed(2) : '—'; },

    statusBadge(status) {
      return {
        completed: 'bg-green-100 text-green-700',
        failed:    'bg-red-100 text-red-600',
        running:   'bg-yellow-100 text-yellow-700',
      }[status] ?? 'bg-gray-100 text-gray-500';
    },

    critBadge(crit) {
      return {
        Prime: 'bg-indigo-100 text-indigo-700',
        RVOL:  'bg-green-100 text-green-700',
        RSM:   'bg-orange-100 text-orange-700',
        STR:   'bg-red-100 text-red-600',
      }[crit] ?? 'bg-gray-100 text-gray-500';
    },

    reasonBadge(reason) {
      return {
        TP1: 'bg-green-100 text-green-700', TP2: 'bg-green-100 text-green-700',
        SL:  'bg-red-100 text-red-600',     BE:  'bg-yellow-100 text-yellow-700',
        EMA10: 'bg-blue-100 text-blue-700', FALSE_BREAKOUT: 'bg-red-100 text-red-500',
      }[reason] ?? 'bg-gray-100 text-gray-500';
    },
  };
}
