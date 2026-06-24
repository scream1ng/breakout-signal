/* lwc-render.js — shared lightweight-charts renderer.
 *
 * window.renderLwcChart(container, D) draws one stock's chart from a
 * get_chart_data() dict (candles, ema10/ema20/sma50/sma200, rvol, signals,
 * trades, hz/tl level segments). Tolerates partial payloads (candles + MAs
 * only, empty signals/trades). Used by the React ChartPanel and the CLI
 * --view standalone. Ported from output/chart_combined.py renderChart().
 *
 * Returns a handle { chart, candle, destroy }. Re-rendering the same
 * container auto-destroys the previous chart first.
 */
(function () {
  /* criteria→color: shared from window.BS when present (SPA); fallback for the standalone --view file */
  const CRIT_FALLBACK = { Prime: '#ec4899', RVOL: '#2563eb', RSM: '#eab308', STR: '#dc2626', SMA50: '#64748b' };

  function destroyOn(container) {
    if (container && container._lwc) {
      try { container._lwc.ro && container._lwc.ro.disconnect(); } catch (e) {}
      try { container._lwc.chart.remove(); } catch (e) {}
      container._lwc = null;
    }
  }

  function renderLwcChart(container, D) {
    if (!container || !D || !D.candles || !D.candles.length) return null;
    if (!window.LightweightCharts) { console.error('lightweight-charts not loaded'); return null; }
    destroyOn(container);
    container.innerHTML = '';

    const LWC = window.LightweightCharts;
    const chart = LWC.createChart(container, {
      autoSize: true,
      layout: { background: { color: '#ffffff' }, textColor: '#374151', fontSize: 11 },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#e5e7eb' },
      timeScale: { borderColor: '#e5e7eb', rightOffset: 5, fixLeftEdge: false },
    });

    // Price scale: leave bottom 28% for volume
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.04, bottom: 0.28 } });

    // ── Candlesticks ──
    const candle = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    });
    candle.setData(D.candles.map(c => ({ time: c.d, open: c.o, high: c.h, low: c.l, close: c.c })));

    // ── Volume (RVOL) histogram — bottom band ──
    const rvolMin = D.rvol_min != null ? D.rvol_min : 1.5;
    const volS = chart.addHistogramSeries({ priceScaleId: 'rvol', lastValueVisible: false, priceLineVisible: false });
    chart.priceScale('rvol').applyOptions({ scaleMargins: { top: 0.86, bottom: 0 }, visible: false });
    volS.setData(D.candles.map(c => ({
      time: c.d, value: c.rv != null ? c.rv : 0,
      color: (c.rv != null && c.rv >= rvolMin) ? 'rgba(22,163,74,0.45)' : 'rgba(209,213,219,0.5)',
    })));
    // RVOL threshold line
    const rvolThresh = chart.addLineSeries({
      priceScaleId: 'rvol', color: 'rgba(217,119,6,0.55)', lineWidth: 1,
      lineStyle: LWC.LineStyle.Dashed, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
    });
    rvolThresh.setData([
      { time: D.candles[0].d, value: rvolMin },
      { time: D.candles[D.candles.length - 1].d, value: rvolMin },
    ]);

    // ── Moving averages ──
    const maList = [
      { key: 'ema10',  color: '#6366f1', width: 1.5, style: LWC.LineStyle.Solid },
      { key: 'ema20',  color: '#f59e0b', width: 1,   style: LWC.LineStyle.Dashed },
      { key: 'sma50',  color: '#ef4444', width: 1.8, style: LWC.LineStyle.Solid },
      { key: 'sma200', color: '#9ca3af', width: 0.9, style: LWC.LineStyle.Dashed },
    ];
    maList.forEach(({ key, color, width, style }) => {
      if (!D[key]) return;
      const ms = chart.addLineSeries({ color, lineWidth: width, lineStyle: style, lastValueVisible: false, priceLineVisible: false });
      const pts = [];
      D.candles.forEach((c, i) => { const v = D[key][i]; if (v != null) pts.push({ time: c.d, value: v }); });
      if (pts.length) ms.setData(pts);
    });

    // ── Level segments (horizontal resistance + trendlines) ──
    const barDate = i => D.candles[Math.max(0, Math.min(D.candles.length - 1, i))].d;
    const addSegLine = (seg, color, width, lineStyle) => {
      if (!seg.xs || seg.xs.length < 2) return;
      const s = chart.addLineSeries({
        color, lineWidth: width, lineStyle: lineStyle != null ? lineStyle : LWC.LineStyle.Solid,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      });
      const dateMap = new Map();
      seg.xs.forEach((x, i) => dateMap.set(barDate(x), seg.ys[i]));
      const pts = [...dateMap.entries()].map(([time, value]) => ({ time, value })).sort((a, b) => a.time < b.time ? -1 : 1);
      if (pts.length >= 2) s.setData(pts);
    };
    (D.hz_fast || []).forEach(seg => addSegLine(seg, 'rgba(249,115,22,0.7)',  1, LWC.LineStyle.Dashed));
    (D.hz_slow || []).forEach(seg => addSegLine(seg, 'rgba(253,186,116,0.7)', 1, LWC.LineStyle.Dashed));
    (D.tl_fast || []).forEach(seg => addSegLine(seg, 'rgba(249,115,22,0.75)',  1.5, LWC.LineStyle.Solid));
    (D.tl_slow || []).forEach(seg => addSegLine(seg, 'rgba(253,186,116,0.75)', 1.5, LWC.LineStyle.Solid));

    // ── Markers: buy (signals, arrowUp by criteria) + sell (trades, arrowDown) ──
    const CRIT_COLOR = (window.BS && window.BS.CRIT_COLOR) || CRIT_FALLBACK;
    const markers = [];
    (D.signals || []).forEach(s => {
      const col = CRIT_COLOR[s.filter_type] || s.col || CRIT_FALLBACK.Prime;
      markers.push({
        time: s.date, position: 'belowBar', color: col, shape: 'arrowUp',
        text: (s.filter_type && s.filter_type !== 'Below') ? s.filter_type : '', size: 1,
      });
    });
    (D.trades || []).forEach(t => {
      const exitColor = t.exit_reason === 'SL' ? '#dc2626'
        : t.exit_reason === 'BE' ? '#f97316'
        : t.exit_reason === 'EMA10' ? '#f59e0b' : '#6b7280';
      if (t.tp1_hit && t.tp1_bar != null && D.candles[t.tp1_bar])
        markers.push({ time: D.candles[t.tp1_bar].d, position: 'aboveBar', color: '#16a34a', shape: 'arrowDown', text: 'TP1', size: 0.7 });
      if (t.tp2_hit && t.tp2_bar != null && D.candles[t.tp2_bar])
        markers.push({ time: D.candles[t.tp2_bar].d, position: 'aboveBar', color: '#15803d', shape: 'arrowDown', text: 'TP2', size: 0.7 });
      if (t.exit_bar != null && D.candles[t.exit_bar] && t.exit_reason !== 'End')
        markers.push({ time: D.candles[t.exit_bar].d, position: 'aboveBar', color: exitColor, shape: 'arrowDown', text: t.exit_reason === 'EMA10' ? 'MA10' : t.exit_reason, size: 0.7 });
    });
    markers.sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
    candle.setMarkers(markers);

    // ── Default visible range: last ~1 year ──
    (function () {
      const lastD = D.candles[D.candles.length - 1].d;
      const fromDt = new Date(lastD);
      fromDt.setFullYear(fromDt.getFullYear() - 1);
      const fromD = fromDt.toISOString().slice(0, 10);
      try { chart.timeScale().setVisibleRange({ from: fromD, to: lastD }); }
      catch (e) { chart.timeScale().fitContent(); }
    })();

    const ro = new ResizeObserver(() => { try { chart.timeScale().fitContent(); } catch (e) {} });
    ro.observe(container);

    const handle = { chart, candle, ro, destroy: () => destroyOn(container) };
    container._lwc = handle;
    return handle;
  }

  window.renderLwcChart = renderLwcChart;
  window.destroyLwcChart = destroyOn;
})();
