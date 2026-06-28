/* bt-screener.jsx — Screener: a Relative Rotation Graph over the SET universe.
 * Default = sector roll-up (one dot per sector, member-averaged RSM, with a
 * rotation tail). Drill into any sector for its members; "All stocks" plots the
 * universe as a density cloud. Axes are median-centered vs peers (rrg.py).
 * Universe comes from /api/screener (built by the EOD scan), passed in as the
 * `universe` prop. Exports window.ScreenerView. */
const { fmt1: sf1, fmt2: sf2, fmt0: sf0 } = window.BS;

function scrHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function scrRng(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

const isNewHigh = (s) => s.off >= -2;

/* short, distinct sector plot labels (full SET names collide: Consumer×3, Health×2) */
const SECTOR_SHORT = {
  'Industrial Services': 'Indust Svc', 'Producer Manufacturing': 'Producer Mfg',
  'Distribution Services': 'Distrib Svc', 'Process Industries': 'Process Ind',
  'Energy Minerals': 'Energy Min', 'Technology Services': 'Tech Svc',
  'Utilities': 'Utilities', 'Consumer Services': 'Cons Svc', 'Finance': 'Finance',
  'Transportation': 'Transport', 'Commercial Services': 'Comm Svc',
  'Electronic Technology': 'Elec Tech', 'Retail Trade': 'Retail',
  'Health Services': 'Health Svc', 'Consumer Non-Durables': 'Cons NonDur',
  'Miscellaneous': 'Misc', 'Consumer Durables': 'Cons Dur',
  'Non-Energy Minerals': 'NonEgy Min', 'Health Technology': 'Health Tech',
};
const sectorShort = (s) => SECTOR_SHORT[s.name] || s.abbr || (s.name || '').slice(0, 8);

const QUAD = {
  leading:   { key: 'leading',   label: 'LEADING',   color: '#0c9b7d', tint: 'rgba(8,153,129,0.07)' },
  improving: { key: 'improving', label: 'IMPROVING', color: '#2f6fe0', tint: 'rgba(47,111,224,0.06)' },
  weakening: { key: 'weakening', label: 'WEAKENING', color: '#d99a2b', tint: 'rgba(217,154,43,0.07)' },
  lagging:   { key: 'lagging',   label: 'LAGGING',   color: '#e0545f', tint: 'rgba(224,84,95,0.06)' },
};
function quadOf(ratio, mom) {
  if (ratio >= 100 && mom >= 100) return QUAD.leading;
  if (ratio < 100 && mom >= 100) return QUAD.improving;
  if (ratio >= 100 && mom < 100) return QUAD.weakening;
  return QUAD.lagging;
}

/* ── fixed 91.5–108.5 pixel frame; data is median-centered (rrg.py) ── */
const RX0 = 91.5, RX1 = 108.5, MY0 = 91.5, MY1 = 108.5;
const PLOT = { w: 620, h: 392, l: 46, r: 30, t: 26, b: 34 };
const iw = PLOT.w - PLOT.l - PLOT.r, ih = PLOT.h - PLOT.t - PLOT.b;
const sx = (v) => PLOT.l + ((v - RX0) / (RX1 - RX0)) * iw;
const sy = (v) => PLOT.t + (1 - (v - MY0) / (MY1 - MY0)) * ih;

/* curved 9-week rotation tail radiating from near centre to current position */
function tail(key, ratio, mom) {
  const sr = 100 + (ratio - 100) * 0.36, sm = 100 + (mom - 100) * 0.36;
  const dx = ratio - sr, dy = mom - sm, len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const rng = scrRng(scrHash(key) ^ 0x51ed);
  const bow = len * 0.26 * (rng() > 0.45 ? 1 : -1);
  const cx1 = (sr + ratio) / 2 + nx * bow, cy1 = (sm + mom) / 2 + ny * bow;
  const N = 9, pts = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1), mt = 1 - t;
    let x = mt * mt * sr + 2 * mt * t * cx1 + t * t * ratio;
    let y = mt * mt * sm + 2 * mt * t * cy1 + t * t * mom;
    if (i > 0 && i < N - 1) { x += (rng() - 0.5) * 0.22; y += (rng() - 0.5) * 0.22; }
    pts.push([sx(x).toFixed(1), sy(y).toFixed(1)]);
  }
  return 'M' + pts.map((p) => p.join(',')).join(' L');
}

/* ── the map ── */
function RotationMap({ nodes, showTails, dotR, labelKeys, selected, onSelect, onActivate, interactive, medX, medY, gainX, gainY }) {
  const cx = sx(100), cy = sy(100);
  const ticks = [94, 97, 100, 103, 106];
  const dim = selected != null;
  const labelSet = labelKeys;
  // map a plot-unit gridline back to a real RSM rating (inverse of rrg.py's
  // plot = 100 + (rsm - median) * gain). Falls back to the plot unit if unknown.
  const rsmLabel = (g, med, gain) => (gain ? Math.round(med + (g - 100) / gain) : g);
  return (
    <svg viewBox={`0 0 ${PLOT.w} ${PLOT.h}`} className="qd-svg" preserveAspectRatio="xMidYMid meet">
      <rect x={cx} y={PLOT.t} width={PLOT.l + iw - cx} height={cy - PLOT.t} fill={QUAD.leading.tint} />
      <rect x={PLOT.l} y={PLOT.t} width={cx - PLOT.l} height={cy - PLOT.t} fill={QUAD.improving.tint} />
      <rect x={cx} y={cy} width={PLOT.l + iw - cx} height={PLOT.t + ih - cy} fill={QUAD.weakening.tint} />
      <rect x={PLOT.l} y={cy} width={cx - PLOT.l} height={PLOT.t + ih - cy} fill={QUAD.lagging.tint} />

      {ticks.map((g) => <g key={'t' + g}>
        <line x1={sx(g)} y1={PLOT.t} x2={sx(g)} y2={PLOT.t + ih} stroke={g === 100 ? '#c4ccd6' : '#eef1f5'} strokeWidth="1" strokeDasharray={g === 100 ? '4 4' : undefined} />
        <line x1={PLOT.l} y1={sy(g)} x2={PLOT.l + iw} y2={sy(g)} stroke={g === 100 ? '#c4ccd6' : '#eef1f5'} strokeWidth="1" strokeDasharray={g === 100 ? '4 4' : undefined} />
        <text x={sx(g)} y={PLOT.t + ih + 13} className="qd-tick" textAnchor="middle">{rsmLabel(g, medX, gainX)}</text>
        <text x={PLOT.l - 7} y={sy(g) + 3} className="qd-tick" textAnchor="end">{rsmLabel(g, medY, gainY)}</text>
      </g>)}

      <text x={PLOT.l + iw - 6} y={PLOT.t + 14} className="qd-qlbl" textAnchor="end" fill={QUAD.leading.color}>LEADING ↗</text>
      <text x={PLOT.l + 6} y={PLOT.t + 14} className="qd-qlbl" textAnchor="start" fill={QUAD.improving.color}>IMPROVING</text>
      <text x={PLOT.l + iw - 6} y={PLOT.t + ih - 7} className="qd-qlbl" textAnchor="end" fill={QUAD.weakening.color}>WEAKENING</text>
      <text x={PLOT.l + 6} y={PLOT.t + ih - 7} className="qd-qlbl" textAnchor="start" fill={QUAD.lagging.color}>LAGGING</text>
      <text x={PLOT.l + iw / 2} y={PLOT.h - 4} className="qd-axt" textAnchor="middle">RSM-100 · established strength  →</text>
      <text x={12} y={PLOT.t + ih / 2} className="qd-axt" textAnchor="middle" transform={`rotate(-90 12 ${PLOT.t + ih / 2})`}>RSM-21 · recent strength  ↑</text>

      {/* non-interactive cloud: plain circles, no per-dot handlers (scales to 1000s) */}
      {!interactive && nodes.map((n) => (
        <circle key={n.key} cx={sx(n.ratio)} cy={sy(n.mom)} r={dotR} fill={n.color} opacity={dim ? (selected === n.key ? 1 : 0.12) : 0.62} />
      ))}

      {/* selected tail in cloud mode */}
      {!interactive && dim && (() => { const n = nodes.find((x) => x.key === selected); if (!n) return null;
        return <g><path d={tail(n.key, n.ratio, n.mom)} fill="none" stroke={n.color} strokeWidth="2.2" opacity="0.85" strokeLinecap="round" />
          <circle cx={sx(n.ratio)} cy={sy(n.mom)} r="7" fill={n.color} stroke="#fff" strokeWidth="1.5" />
          <text x={sx(n.ratio)} y={sy(n.mom) - 12} className="qd-tk sel" textAnchor="middle">{n.tk}</text></g>; })()}

      {/* interactive nodes */}
      {interactive && nodes.map((n) => {
        const isSel = selected === n.key, faded = dim && !isSel;
        const ccx = sx(n.ratio), ccy = sy(n.mom);
        const showLabel = (labelSet && labelSet.has(n.key)) || isSel;
        const drawTail = showTails || isSel;
        return (
          <g key={n.key} opacity={faded ? 0.16 : 1} style={{ cursor: 'pointer' }}
             onMouseEnter={() => onSelect(n.key)} onMouseLeave={() => onSelect(null)}
             onClick={() => onActivate && onActivate(n)}>
            {drawTail && <path d={tail(n.key, n.ratio, n.mom)} fill="none" stroke={n.color} strokeWidth={isSel ? 2.4 : 1.5} opacity={isSel ? 0.85 : 0.45} strokeLinecap="round" strokeLinejoin="round" />}
            {n.newHigh && <circle cx={ccx} cy={ccy} r={isSel ? 12 : 9.5} fill="none" stroke="#d99a2b" strokeWidth="1.5" />}
            <circle cx={ccx} cy={ccy} r={isSel ? (n.big ? 9 : 6) : (n.big ? 7 : dotR)} fill={n.color} stroke="#fff" strokeWidth={n.big ? 1.5 : 1} />
            {showLabel && (() => {
              const lx = Math.min(Math.max(ccx, PLOT.l + 16), PLOT.l + iw - 16);
              const ly = Math.max(ccy - (isSel ? 14 : 11), PLOT.t + 9);
              return <text x={lx} y={ly} className={`qd-tk ${isSel ? 'sel' : ''}`} textAnchor="middle">{n.tk}</text>;
            })()}
          </g>
        );
      })}
    </svg>
  );
}

/* ── leaderboard rows ── */
function SectorRow({ s, rank, selected, onSelect, onActivate }) {
  const q = quadOf(s.ratio, s.mom), up = s.mom >= 100;
  return (
    <div className={`ld-row sec ${selected === s.id ? 'sel' : ''}`} style={{ '--q': q.color }}
         onMouseEnter={() => onSelect(s.id)} onMouseLeave={() => onSelect(null)} onClick={() => onActivate(s)}>
      <span className="ld-rank mono">{rank}</span>
      <span className="ld-tk">{s.name}<span className="ld-sector">{s.members.length} stocks · {s.members.filter((m) => quadOf(m.ratio, m.mom).key === 'leading').length} leading</span></span>
      <span className="ld-rs mono" style={{ color: q.color }}>{sf0(s.rsm100)}</span>
      <span className={`ld-mo mono ${up ? 'g' : 'r'}`}>{up ? '▲' : '▼'}{sf0(s.rsm21)}</span>
      <span className="ld-drill">›</span>
    </div>
  );
}
function StockRow({ s, rank, selected, onSelect, onActivate }) {
  const q = quadOf(s.ratio, s.mom), up = s.mom >= 100, nh = isNewHigh(s);
  return (
    <div className={`ld-row st ${selected === s.tk ? 'sel' : ''}`} style={{ '--q': q.color, cursor: 'pointer' }}
         onMouseEnter={() => onSelect(s.tk)} onMouseLeave={() => onSelect(null)} onClick={() => onActivate(s)}>
      <span className="ld-rank mono">{rank}</span>
      <span className="ld-tk">{s.tk}<span className="ld-sector">{s.sectorName}</span></span>
      <span className="ld-rs mono" style={{ color: q.color }}>{sf0(s.rsm100)}</span>
      <span className={`ld-mo mono ${up ? 'g' : 'r'}`}>{up ? '▲' : '▼'}{sf0(s.rsm21)}</span>
      <span className={`ld-m1 mono ${s.m1 >= 0 ? 'g' : 'r'}`}>{s.m1 > 0 ? '+' : ''}{sf1(s.m1)}%</span>
      <span className="ld-flag">{nh ? <span className="ld-newhi">NEW HIGH</span> : s.st > 0 ? <span className="ld-streak">▲{s.st}w</span> : <span className="ld-streak flat">—</span>}</span>
    </div>
  );
}

const STRENGTH = (x) => x.ratio + x.mom;
const ROW_CAP = 150;

function ScreenerPage({ UNIV }) {
  const [view, setView] = React.useState({ level: 'sector', sector: null }); // sector | stock(sector) | stock(null=all)
  const [sel, setSel] = React.useState(null);
  const [tails, setTails] = React.useState(true);
  const [chartItem, setChartItem] = React.useState(null);   // stock chart shown in left pane (null = rotation map)

  const sectorObj = view.sector ? UNIV.sectors.find((s) => s.id === view.sector) : null;

  // build map nodes + leaderboard for current view
  const isSectorView = view.level === 'sector';
  const isAll = view.level === 'stock' && view.sector == null;

  let nodes, labelKeys, dotR, board, boardKind, boardCount;
  if (isSectorView) {
    nodes = UNIV.sectors.map((s) => ({ key: s.id, id: s.id, tk: sectorShort(s), ratio: s.ratio, mom: s.mom, color: quadOf(s.ratio, s.mom).color, big: true }));
    labelKeys = new Set(nodes.map((n) => n.key));
    dotR = 7;
    board = [...UNIV.sectors].sort((a, b) => STRENGTH(b) - STRENGTH(a));
    boardKind = 'sector'; boardCount = UNIV.sectors.length;
  } else {
    const filtered = isAll ? UNIV.stocks : (sectorObj ? sectorObj.members : []);
    nodes = filtered.map((s) => ({ key: s.tk, tk: s.tk, ratio: s.ratio, mom: s.mom, color: quadOf(s.ratio, s.mom).color, newHigh: isNewHigh(s) && !isAll, big: false, sectorName: s.sectorName, rsm21: s.rsm21 }));
    // label only the strongest handful (+ hovered) to avoid clutter
    const lead = [...filtered].sort((a, b) => STRENGTH(b) - STRENGTH(a)).slice(0, isAll ? 0 : 14);
    labelKeys = new Set(lead.map((s) => s.tk));
    dotR = isAll ? 2.3 : 3.6;
    board = [...filtered].sort((a, b) => STRENGTH(b) - STRENGTH(a));
    boardKind = 'stock'; boardCount = filtered.length;
  }

  const interactive = !isAll;        // cloud mode is static for performance
  const boardRows = board.slice(0, ROW_CAP);

  // header stat tiles — scoped to the current view (drilled sector → its members, else whole universe).
  // Single pass, memoized: recompute only when the scope changes, not on hover/toggle.
  const { hStrong, hLead, hNew } = React.useMemo(() => {
    const scope = sectorObj ? sectorObj.members : UNIV.stocks;
    let strong = 0, lead = 0, nh = 0;
    for (const s of scope) {
      if (s.rsm100 >= 80) strong++;
      if (quadOf(s.ratio, s.mom).key === 'leading') lead++;
      if (isNewHigh(s)) nh++;
    }
    return { hStrong: strong, hLead: lead, hNew: nh };
  }, [sectorObj, UNIV]);
  const hCount = isSectorView ? UNIV.sectors.length : (sectorObj ? sectorObj.members.length : UNIV.total);
  const headTitle = isSectorView ? 'Sector Rotation' : (sectorObj ? sectorObj.name : 'All Stocks');
  const headScope = isSectorView ? `${UNIV.total.toLocaleString()} stocks` : (sectorObj ? `${sectorObj.members.length} stocks` : `${UNIV.total.toLocaleString()} names`);

  const goSector = () => { setView({ level: 'sector', sector: null }); setSel(null); setChartItem(null); };
  const drillSector = (s) => { setView({ level: 'stock', sector: s.id }); setSel(null); setChartItem(null); };
  const goAll = () => { setView({ level: 'stock', sector: null }); setSel(null); setChartItem(null); };
  const openStock = (x) => setChartItem({ ticker: x.tk, sector: x.sectorName, rsm: x.rsm100 });

  return (
    <div className="ws">
      <div className="ws-chart">
        {chartItem ? (
          <div className="scr-chart">
            <button className="scr-back" onClick={() => setChartItem(null)}>‹ Back to rotation map</button>
            <div className="scr-chart-canvas"><window.ChartPanel item={chartItem} /></div>
          </div>
        ) : (
        <div className="qd-card scr-mapcard">
          <div className="cc-head">
            <div style={{ minWidth: 0 }}>
              <div className="cc-sym">
                <span className="cc-tk">{headTitle}</span>
                <span className="cc-exch">SET</span>
                <span className="cc-sector">{headScope}</span>
              </div>
              <div className="qd-crumb" style={{ marginTop: 7 }}>
                <button className={`qd-cb ${isSectorView ? 'on' : ''}`} onClick={goSector}>Sectors</button>
                {sectorObj && <><span className="qd-sep">›</span><button className="qd-cb on">{sectorObj.name}</button></>}
                <span className="qd-sep">·</span>
                <button className={`qd-cb ${isAll ? 'on' : ''}`} onClick={goAll}>All {UNIV.total.toLocaleString()}</button>
                <span className="qd-sep">·</span>
                <span className="qd-crumb-sub">{isSectorView ? 'Each dot is a sector (member-averaged RSM) with its rotation tail · median-centered vs peers' : isAll ? 'Every stock as a density cloud — hover the leaderboard to isolate one' : 'Leaders labeled · click any name to chart it'}</span>
              </div>
            </div>
            <div className="qd-headright">
              <div className="cc-hstats">
                <div className="cc-hstat"><span className="l">{isSectorView ? 'Sectors' : 'Names'}</span><span className="v mono">{hCount.toLocaleString()}</span></div>
                <div className="cc-hstat"><span className="l">Strong ≥80</span><span className="v mono" style={{ color: 'var(--green)' }}>{hStrong}</span></div>
                <div className="cc-hstat"><span className="l">Leading</span><span className="v mono">{hLead}</span></div>
                <div className="cc-hstat"><span className="l">New highs</span><span className="v mono" style={{ color: '#b8860b' }}>{hNew}</span></div>
              </div>
              <div className="qd-tools">
                {interactive && <label className="qd-toggle"><input type="checkbox" checked={tails} onChange={(e) => setTails(e.target.checked)} />tails</label>}
                <div className="scr-legend"><span><i className="scr-lg ring" /> new high</span></div>
              </div>
            </div>
          </div>
          <RotationMap nodes={nodes} showTails={tails && !isAll} dotR={dotR} labelKeys={labelKeys}
            selected={sel} onSelect={setSel} onActivate={isSectorView ? drillSector : openStock} interactive={interactive}
            medX={UNIV.median_rsm100} medY={UNIV.median_rsm21} gainX={UNIV.gain_x} gainY={UNIV.gain_y} />
          <div className="qd-foot">
            {isSectorView ? <span>Click a sector to drill into its stocks.</span>
              : <span>Showing <b>{boardCount.toLocaleString()}</b> {isAll ? 'stocks' : 'names'}. Click any name to chart it.</span>}
          </div>
        </div>
        )}
      </div>

      <div className="ws-side">
        <div className="ld-card scr-ldcard">
          <div className="ld-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              {!isSectorView && <button className="ld-back" onClick={goSector}>‹ Sectors</button>}
              <span className="ld-h-title">{isSectorView ? 'Sector strength' : sectorObj ? sectorObj.name : 'All stocks'}</span>
            </div>
            {boardKind === 'sector' && <span className="ld-h-sub">RSM-100 / RSM-21</span>}
          </div>
          <div className={`ld-cols ${boardKind}`}>
            <span>#</span><span>{isSectorView ? 'Sector' : 'Symbol'}</span><span className="r">RSM100</span><span className="r">RSM21</span>
            {boardKind === 'stock' ? <><span className="r">1M</span><span className="r">Signal</span></> : <span className="r">→</span>}
          </div>
          <div className="ld-body">
            {boardKind === 'sector'
              ? board.map((s, i) => <SectorRow key={s.id} s={s} rank={i + 1} selected={sel} onSelect={setSel} onActivate={drillSector} />)
              : boardRows.map((s, i) => <StockRow key={s.tk} s={s} rank={i + 1} selected={sel} onSelect={setSel} onActivate={openStock} />)}
            {boardKind === 'stock' && boardCount > ROW_CAP && <div className="ld-more">+ {(boardCount - ROW_CAP).toLocaleString()} more</div>}
            {boardKind === 'stock' && boardCount === 0 && <div className="ld-more">No stocks in this sector</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* Top-level tab view: handles the loading / empty universe states, then renders
 * the rotation map once real data is in. */
function ScreenerView({ universe }) {
  if (universe === null || universe === undefined) {
    return <div className="page"><div className="loading">Loading screener…</div></div>;
  }
  if (universe === false) {
    return <div className="page"><div className="loading">Screener data unavailable.</div></div>;
  }
  if (!universe.total) {
    return (
      <div className="page">
        <div className="page-head"><div><h1 className="page-t">Screener</h1>
          <p className="page-sub">No screener universe yet — run an EOD scan to build the Relative Rotation Graph.</p></div></div>
      </div>
    );
  }
  return <ScreenerPage UNIV={universe} />;
}

Object.assign(window, { ScreenerView });
