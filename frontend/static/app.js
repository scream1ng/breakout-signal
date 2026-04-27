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
    wlSort:           'pct_to_level',
    wlSortDir:        1,
    runDetailModal:   null,   // JobRun dict to show in popup
    jobRunning:       {},
    notifyTesting:    {},
    toast:            { msg: '', ok: true },
    _refreshTimer:    null,

    // ── Dashboard session helpers ───────────────────────────────────────
    bkkNowParts() {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      }).formatToParts(new Date());
      const get = (k) => Number(parts.find(p => p.type === k)?.value || 0);
      return {
        year: get('year'), month: get('month'), day: get('day'),
        hour: get('hour'), minute: get('minute'),
      };
    },

    bkkDateIso() {
      const p = this.bkkNowParts();
      return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
    },

    isMarketOpenOrLater() {
      const p = this.bkkNowParts();
      return (p.hour * 60 + p.minute) >= (10 * 60);
    },

    get dashboardIntradayRows() {
      const rows = this.signals?.alerted_today || [];
      if (!this.isMarketOpenOrLater()) return rows;
      return this.signals?.alert_date === this.bkkDateIso() ? rows : [];
    },

    get dashboardFakeoutRows() {
      const rows = this.signals?.failed_today || [];
      if (!this.isMarketOpenOrLater()) return rows;
      return this.signals?.alert_date === this.bkkDateIso() ? rows : [];
    },

    get dashboardEodRows() {
      const rows = this.scanLatest?.signals || [];
      if (!this.isMarketOpenOrLater()) return rows;
      return this.scanLatest?.date === this.bkkDateIso() ? rows : [];
    },

    getRunResult(run) {
      try {
        const obj = run?.result_json ? JSON.parse(run.result_json) : {};
        return obj && typeof obj === 'object' ? obj : {};
      } catch {
        return {};
      }
    },

    runLogText(run) {
      const result = this.getRunResult(run);
      const stdout = String(result.stdout || '').trim();
      const stderr = String(result.stderr || '').trim();
      if (!stdout && !stderr) return '';
      return [
        'STDOUT:',
        stdout || '(empty)',
        '',
        'STDERR:',
        stderr || '(empty)',
      ].join('\n');
    },

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
        setTimeout(() => { this.toast = { msg: '', ok: true }; }, 3000);
        // Poll until the job is no longer running (max 5 min)
        const poll = async (attempts = 0) => {
          if (attempts > 150) return;
          await this.loadSystem();
          const last = this.lastRuns[jobName] ?? {};
          if (last.status === 'running') setTimeout(() => poll(attempts + 1), 2000);
          else this.jobRunning = { ...this.jobRunning, [jobName]: false };
        };
        setTimeout(() => poll(), 2000);
      } catch (e) {
        this.toast = { msg: `Failed to trigger ${jobName}`, ok: false };
        setTimeout(() => { this.toast = { msg: '', ok: true }; }, 3000);
        this.jobRunning = { ...this.jobRunning, [jobName]: false };
      }
    },

    async testNotify(channel) {
      this.notifyTesting = { ...this.notifyTesting, [channel]: true };
      try {
        const response = await fetch(`/api/notify/test/${channel}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || `Failed to send ${channel} test`);
        }
        this.toast = { msg: `${data.channel.toUpperCase()} test notification sent`, ok: true };
      } catch (e) {
        this.toast = { msg: e.message || `Failed to send ${channel} test`, ok: false };
      } finally {
        this.notifyTesting = { ...this.notifyTesting, [channel]: false };
        setTimeout(() => { this.toast = { msg: '', ok: true }; }, 3000);
      }
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
        if (key === 'ticker') {
          return dir * (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0);
        }
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
      const STALE_MS = 15 * 60 * 1000;  // 15 minutes
      const jobs = [
        { id: 'eod_scan',      label: 'EOD Scan',       nextKey: 'eod_scan' },
        { id: 'intraday_scan', label: 'Intraday Scan',  nextKey: 'intraday_scan' },
        { id: 'review_scan',   label: 'Fakeout Review', nextKey: 'review_scan' },
      ];
      return jobs.map(j => {
        const last     = this.lastRuns[j.id] ?? {};
        let   status   = last.status ?? 'never';
        // Detect stale-running: job stuck in 'running' for > 15 min
        if (status === 'running' && last.started_at) {
          const age = Date.now() - new Date(last.started_at).getTime();
          if (age > STALE_MS) status = 'stale';
        }
        const dotClass = { completed: 'dot-green', failed: 'dot-red', stale: 'dot-red',
                           running: 'dot-yellow', never: 'dot-grey' }[status] ?? 'dot-grey';
        return {
          name:        j.id,
          label:       j.label,
          statusClass: dotClass,
          lastRun:     last.started_at ? this.fmtDatetime(last.started_at) : '—',
          duration:    last.duration_s != null ? last.duration_s.toFixed(1) + 's' : '—',
          nextRun:     this.nextRuns[j.nextKey] ? this.fmtDatetime(this.nextRuns[j.nextKey]) : '—',
          error:       last.error ?? (status === 'stale' ? 'Job appears stuck (>15 min). Restart server to reset.' : null),
          running:     !!this.jobRunning[j.id],
        };
      });
    },

    wlGroupList() {
      const detail = this.watchlistDetail;
      if (!detail) return [];

      const normalized = {
        '> MA10': [],
        '> MA20': [],
        '> MA50': [],
        'Other': [],
      };
      const seen = new Set();

      const normalizeKey = (raw) => {
        const text = String(raw || '').toUpperCase().replace(/\s+/g, '');
        if (text.includes('MA10') || text.includes('EMA10')) return '> MA10';
        if (text.includes('MA20') || text.includes('EMA20')) return '> MA20';
        if (text.includes('MA50') || text.includes('SMA50')) return '> MA50';
        return 'Other';
      };

      const detectFromItem = (item) => {
        const rawGroup = item?.ma_group || item?.group || item?.maGroup;
        if (rawGroup) return normalizeKey(rawGroup);
        if (item?.above_ema10 || item?.above_ma10) return '> MA10';
        if (item?.above_ema20 || item?.above_ma20) return '> MA20';
        if (item?.above_sma50 || item?.above_ma50) return '> MA50';
        return 'Other';
      };

      const itemKey = (item) => {
        const t = String(item?.ticker_full || item?.ticker || '').toUpperCase();
        return t || JSON.stringify(item || {});
      };

      const pushUnique = (key, item) => {
        const k = itemKey(item);
        if (seen.has(k)) return;
        seen.add(k);
        normalized[key].push(item);
      };

      Object.entries(detail.groups || {}).forEach(([rawKey, items]) => {
        const key = normalizeKey(rawKey);
        (items || []).forEach((item) => {
          pushUnique(key, item);
        });
      });

      (detail.items || []).forEach((item) => {
        const key = detectFromItem(item);
        pushUnique(key, item);
      });

      return ['> MA10', '> MA20', '> MA50', 'Other']
        .map(key => ({ key, items: normalized[key] }))
        .filter(g => g.items.length > 0);
    },

    wlSortedGroup(items) {
      if (!items || !items.length) return [];
      const key = this.wlSort;
      const dir = this.wlSortDir;
      return [...items].sort((a, b) => {
        let av, bv;
        if (key === 'pct_to_level') {
          const aL = a.levels?.[0]?.level, aC = a.close;
          const bL = b.levels?.[0]?.level, bC = b.close;
          av = (aL && aC) ? (aL - aC) / aC * 100 : 9999;
          bv = (bL && bC) ? (bL - bC) / bC * 100 : 9999;
        } else if (key === 'rsm') {
          av = a.rsm ?? -1; bv = b.rsm ?? -1;
        } else if (key === 'rvol') {
          av = a.rvol ?? -1; bv = b.rvol ?? -1;
        } else if (key === 'stretch') {
          av = a.stretch ?? 9999; bv = b.stretch ?? 9999;
        } else if (key === 'close') {
          av = a.close ?? 0; bv = b.close ?? 0;
        } else if (key === 'level') {
          av = a.levels?.[0]?.level ?? 0; bv = b.levels?.[0]?.level ?? 0;
        } else {
          return dir * ((a.ticker || '') < (b.ticker || '') ? -1 : 1);
        }
        return dir * (av - bv);
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
    kindLabel(row) {
      const kind = String(row?.kind || '').toLowerCase();
      if (kind === 'tl') {
        return row?.tl_angle != null ? `TL (${Number(row.tl_angle).toFixed(0)}°)` : 'TL';
      }
      return 'Hz';
    },
    critTextClass(crit) {
      return {
        Prime: 'text-indigo-600',
        RVOL: 'text-green-600',
        RSM: 'text-orange-600',
        STR: 'text-red-600',
        SMA50: 'text-gray-500',
      }[crit] ?? 'text-gray-500';
    },

    statusBadge(status) {
      return {
        completed: 'bg-green-100 text-green-700',
        failed:    'bg-red-100 text-red-600',
        stale:     'bg-orange-100 text-orange-600',
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
