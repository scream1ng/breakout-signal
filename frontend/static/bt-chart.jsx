/* bt-chart.jsx — native React chart panel (replaces the /chart iframe).
 * Fetches /api/chart/{ticker} and renders with the shared window.renderLwcChart.
 * Props: { ticker } — a signal/watchlist item object or a ticker string. */
const { tickerText: _tk, tickerFull: _tkFull, fmt2: _f2 } = window.BS;

function ChartPanel({ ticker }) {
  const wrapRef = React.useRef(null);
  const [state, setState] = React.useState({ status: 'idle', data: null });

  const tkFull = ticker ? _tkFull(ticker) : null;
  const tkShort = ticker ? _tk(ticker) : null;

  React.useEffect(() => {
    if (!tkFull) { setState({ status: 'idle', data: null }); return; }
    let cancelled = false;
    setState({ status: 'loading', data: null });
    fetch(`/api/chart/${encodeURIComponent(tkFull)}`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(d => {
        if (cancelled) return;
        if (!d || !d.candles || !d.candles.length) { setState({ status: 'empty', data: null }); return; }
        setState({ status: 'ready', data: d });
      })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }); });
    return () => { cancelled = true; };
  }, [tkFull]);

  /* Draw after data lands; tear down on unmount / ticker change */
  React.useEffect(() => {
    if (state.status === 'ready' && wrapRef.current && state.data) {
      window.renderLwcChart(wrapRef.current, state.data);
    }
    return () => { if (wrapRef.current) window.destroyLwcChart(wrapRef.current); };
  }, [state]);

  const D = state.data;
  const close = D ? (D.last_close ?? D.candles?.[D.candles.length - 1]?.c) : null;
  const partial = D && D.partial;

  return (
    <div className="chart-wrap">
      <div className="chart-tk-bar">
        <span className="chart-tk-lbl">{tkShort || '—'}</span>
        {close != null && <span style={{ marginLeft: 10, color: 'var(--ink)' }}>฿{_f2(close)}</span>}
        {partial && <span style={{ marginLeft: 10, fontSize: 10, color: 'var(--mut2)' }}>candles + MAs only</span>}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12, fontSize: 10, color: 'var(--mut2)' }}>
          <span style={{ color: '#6366f1' }}>━ EMA10</span>
          <span style={{ color: '#f59e0b' }}>┄ EMA20</span>
          <span style={{ color: '#ef4444' }}>━ SMA50</span>
        </span>
      </div>
      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        {state.status === 'loading' && <div className="loading">Loading chart…</div>}
        {state.status === 'idle' && <div className="loading">Select a ticker to load its chart</div>}
        {state.status === 'empty' && <div className="loading">No chart data for {tkShort}</div>}
        {state.status === 'error' && <div className="loading">Failed to load chart for {tkShort}</div>}
        <div ref={wrapRef} style={{ position: 'absolute', inset: 0, display: state.status === 'ready' ? 'block' : 'none' }} />
      </div>
    </div>
  );
}

Object.assign(window, { ChartPanel });
