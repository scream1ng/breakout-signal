/* bt-chart.jsx — native chart panel (design cc-panel chrome + real lightweight-charts).
 * Header/stat strip come instantly from the selected item; candles are fetched
 * from /api/chart/{ticker} and drawn via window.renderLwcChart. */
const { tickerText: _tk, tickerFull: _tkFull, fmt1: _f1, fmt2: _f2, kindLabel: _kind, CC: _CC } = window.BS;

/* per-session cache: chart payloads are heavy and the DB may be remote — re-selecting a ticker should be instant */
const CHART_CACHE = new Map();

function ChartPanel({ item }) {
  const wrapRef = React.useRef(null);
  const [state, setState] = React.useState({ status: 'idle', data: null });

  const tkFull = item ? _tkFull(item) : null;

  React.useEffect(() => {
    if (!tkFull) { setState({ status: 'idle', data: null }); return; }
    if (CHART_CACHE.has(tkFull)) { setState({ status: 'ready', data: CHART_CACHE.get(tkFull) }); return; }
    let cancelled = false;
    setState({ status: 'loading', data: null });
    fetch(`/api/chart/${encodeURIComponent(tkFull)}`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(d => {
        if (cancelled) return;
        if (!d || !d.candles || !d.candles.length) { setState({ status: 'empty', data: null }); return; }
        CHART_CACHE.set(tkFull, d);
        setState({ status: 'ready', data: d });
      })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }); });
    return () => { cancelled = true; };
  }, [tkFull]);

  React.useEffect(() => {
    if (state.status === 'ready' && wrapRef.current && state.data) {
      window.renderLwcChart(wrapRef.current, state.data);
    }
    return () => { if (wrapRef.current) window.destroyLwcChart(wrapRef.current); };
  }, [state.data]);   // redraw only when the payload changes, not on every status flip

  /* live overlay: when the selected row's price updates (each intraday scan),
   * push it onto the chart's last candle so you watch it cross the level */
  const liveClose = item ? (item.close ?? null) : null;
  React.useEffect(() => {
    if (state.status === 'ready' && liveClose != null && wrapRef.current) {
      window.updateLwcLast(wrapRef.current, liveClose);
    }
  }, [liveClose, state.status]);

  if (!item) {
    return (
      <div className="cc-panel cc-empty">
        <div className="cc-empty-glyph">∿</div>
        <div className="cc-empty-msg">Select a ticker to load its chart</div>
      </div>
    );
  }

  const tk     = _tk(item);
  const D      = state.data;
  const close  = item.close ?? (D ? D.last_close : null);
  const level  = item.level ?? item.bp ?? item.levels?.[0]?.level ?? null;
  const chg    = (level && close) ? ((close - level) / level) * 100 : null;
  const above  = level == null ? true : (close ?? 0) >= level;
  const rvol   = item.proj_rvol ?? item.rvol ?? null;
  const rsm    = item.rsm ?? null;
  const str    = item.stretch ?? null;
  const crit   = item.criteria || item.filter_type || null;
  const partial = D && D.partial;

  return (
    <div className="cc-panel">
      <div className="cc-head">
        <div>
          <div className="cc-sym">
            <span className="cc-tk">{tk}</span>
            <span className="cc-exch">SET</span>
            {item.sector && <span className="cc-sector">{item.sector}</span>}
          </div>
          <div className="cc-price-row">
            <span className="cc-last mono">฿{_f2(close)}</span>
            {level != null && chg != null &&
              <span className={`cc-chg mono ${above ? 'up' : 'dn'}`}>{above ? '▲' : '▼'} {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>}
            <span className="cc-vs mono">vs level ฿{level != null ? _f2(level) : '—'}</span>
          </div>
        </div>
        <div className="cc-hstats">
          <div className="cc-hstat"><span className="l">RVol</span><span className="v mono" style={{ color: rvol >= 2 ? 'var(--green)' : 'var(--navy)' }}>{rvol != null ? _f1(rvol) + '×' : '—'}</span></div>
          <div className="cc-hstat"><span className="l">RSM</span><span className="v mono" style={{ color: rsm >= 80 ? 'var(--green)' : 'var(--navy)' }}>{rsm != null ? Math.round(rsm) : '—'}</span></div>
          <div className="cc-hstat"><span className="l">STR</span><span className="v mono" style={{ color: str > 4 ? 'var(--red)' : 'var(--navy)' }}>{str != null ? _f1(str) + '×' : '—'}</span></div>
        </div>
      </div>
      <div className="cc-legend mono">
        <span><i className="lg-e10"></i> EMA10</span>
        <span><i className="lg-e20"></i> EMA20</span>
        <span><i className="lg-s50"></i> SMA50</span>
        <span><i className="lg-lv"></i> Level</span>
        <span className="cc-kind">{_kind(item)}</span>
        {crit && <span className={`bg ${_CC[crit] || ''}`}>{crit}</span>}
        {partial && <span style={{ color: 'var(--mut3)' }}>· candles + MAs only</span>}
      </div>
      <div className="cc-canvas-wrap">
        {state.status === 'loading' && <div className="cc-loading">Loading chart…</div>}
        {state.status === 'empty' && <div className="cc-loading">No chart data for {tk}</div>}
        {state.status === 'error' && <div className="cc-loading">Failed to load chart for {tk}</div>}
        <div ref={wrapRef} style={{ position: 'absolute', inset: 0, display: state.status === 'ready' ? 'block' : 'none' }} />
      </div>
    </div>
  );
}

Object.assign(window, { ChartPanel });
