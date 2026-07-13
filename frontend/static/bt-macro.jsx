/* bt-macro.jsx — "Macro Map" page for Breakout Signal.
 * One-page global macro dashboard: choropleth world map (countries colored by
 * their headline index's RSM-21 vs ACWI), gauge strip, major-index list
 * grouped by region, and commodities / crypto / FX panels. Real geometry from
 * world-atlas via d3-geo (window.d3 + window.topojson). Data via /api/macro
 * (app/core/macro.py — RSM computed with the project's own rsm.py formula,
 * benchmarked against ACWI; "hot" classification also computed server-side
 * so every view reads the same field). Exports window.MacroPage. */
const { fmt0: mf0, fmt2: mf2 } = window.BS;

/* ── color scale: RSM rating (1-99, IBD curve) → red/amber/green ─────────── */
function hexLerp(a, b, t) {
  const pa = [parseInt(a.slice(1, 3), 16), parseInt(a.slice(3, 5), 16), parseInt(a.slice(5, 7), 16)];
  const pb = [parseInt(b.slice(1, 3), 16), parseInt(b.slice(3, 5), 16), parseInt(b.slice(5, 7), 16)];
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
}
function rsmColor(v) {
  const t = Math.max(0, Math.min(1, (v - 30) / (85 - 30)));
  return t < 0.5 ? hexLerp('#e0545f', '#e3a72e', t * 2) : hexLerp('#e3a72e', '#0c9b7d', (t - 0.5) * 2);
}
const UNTRACKED = '#eef2f6';
function lastRsm(e) { return e.rsm_hist && e.rsm_hist.length ? e.rsm_hist[e.rsm_hist.length - 1] : null; }

const pctTxt = (v, dp = 2) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(dp) + '%';
const cls = (v) => (v >= 0 ? 'up' : 'dn');

function MiniHisto({ hist, w = 58, h = 22 }) {
  const vals = hist && hist.length ? hist : [];
  if (!vals.length) return <svg className="mm-histo" width={w} height={h} aria-hidden="true" />;
  const MIN = 18, MAX = 96, n = vals.length, gap = 1, bw = (w - gap * (n - 1)) / n;
  return (
    <svg className="mm-histo" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      {vals.map((v, i) => {
        const bh = Math.max(2, ((v - MIN) / (MAX - MIN)) * (h - 2));
        return <rect key={i} x={(i * (bw + gap)).toFixed(1)} y={(h - bh).toFixed(1)} width={bw.toFixed(1)} height={bh.toFixed(1)} rx="1" fill={rsmColor(v)} />;
      })}
    </svg>
  );
}

/* ── world map (d3-geo choropleth) ──────────────────────────────────────── */
const MAP_W = 820, MAP_H = 300;
function WorldMap({ countryByIso, hovered, setHovered }) {
  const [feats, setFeats] = React.useState(null);
  const [err, setErr] = React.useState(false);

  React.useEffect(() => {
    let ok = true;
    fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')
      .then((r) => r.json())
      .then((w) => { if (!ok) return; setFeats(window.topojson.feature(w, w.objects.countries).features); })
      .catch(() => { if (ok) setErr(true); });
    return () => { ok = false; };
  }, []);

  const { path, proj } = React.useMemo(() => {
    const bbox = { type: 'Polygon', coordinates: [[[-180, 74], [180, 74], [180, -56], [-180, -56], [-180, 74]]] };
    const p = window.d3.geoEquirectangular().fitExtent([[2, 2], [MAP_W - 2, MAP_H - 2]], bbox);
    return { path: window.d3.geoPath(p), proj: p };
  }, []);
  const grat = React.useMemo(() => path(window.d3.geoGraticule10()), [path]);
  const home = countryByIso['764'];
  const th = home ? proj([100.99, 15.2]) : null;

  if (err) return <div className="mm-maploading">Map data unavailable offline</div>;
  if (!feats) return <div className="mm-maploading"><span className="mm-mapspin"></span>Loading world map…</div>;

  return (
    <svg className="mm-svg" viewBox={`0 0 ${MAP_W} ${MAP_H}`} role="img" aria-label="World markets choropleth">
      <path className="mm-sphere" d={path({ type: 'Sphere' })} />
      <path className="mm-grat" d={grat} />
      {feats.map((f, fi) => {
        const d = countryByIso[f.id];
        const rsm = d ? lastRsm(d) : null;
        const isH = hovered === f.id;
        return (
          <path key={f.id ?? 'f' + fi} className={`mm-country ${isH ? 'hl' : ''}`}
            d={path(f)} fill={rsm != null ? rsmColor(rsm) : UNTRACKED}
            onMouseEnter={d ? () => setHovered(f.id) : undefined}
            onMouseLeave={d ? () => setHovered(null) : undefined} />
        );
      })}
      {feats.map((f, fi) => {
        const d = countryByIso[f.id];
        if (!d || !d.hot) return null;
        const [cx, cy] = path.centroid(f);
        if (isNaN(cx) || isNaN(cy)) return null;
        return <text key={'hot' + (f.id ?? fi)} x={cx} y={cy + 4} textAnchor="middle" fontSize="13" style={{ pointerEvents: 'none' }}>🔥</text>;
      })}
      {th && <>
        <circle className="mm-th-ring" cx={th[0]} cy={th[1]} r="7" />
        <circle cx={th[0]} cy={th[1]} r="2.2" fill="var(--blue)" />
        <text className="mm-th-lbl" x={th[0]} y={th[1] - 11} textAnchor="middle">SET</text>
      </>}
    </svg>
  );
}

function MapReadout({ countryByIso, hovered }) {
  const d = hovered ? countryByIso[hovered] : countryByIso['764'];
  if (!d) return null;
  return (
    <div className="mm-readout">
      <div className="mm-ro-ctry">{d.ctry}{d.home && <span className="mm-ro-home">HOME</span>}{d.hot && <HotBadge />}</div>
      <div className="mm-ro-idx">{d.idx}</div>
      <div className="mm-ro-row">
        <span className="mm-ro-last mono">{mf0(d.last)}</span>
        <span className={`mm-ro-chg mono ${cls(d.chg)}`}>{pctTxt(d.chg)}</span>
      </div>
      <div className="mm-ro-histo">
        <MiniHisto hist={d.rsm_hist} w={120} h={30} />
        <span className="mm-ro-histo-lbl mono">RSM-21 vs ACWI · wk {pctTxt(d.wk, 1)}</span>
      </div>
    </div>
  );
}

/* ── index list row ─────────────────────────────────────────────────────── */
const REGIONS = ['Americas', 'Europe', 'Asia-Pacific', 'MEA'];
const REGION_LABEL = { Americas: 'Americas', Europe: 'Europe', 'Asia-Pacific': 'Asia-Pacific', MEA: 'Middle East · Africa' };

function HotBadge() { return <span className="mm-hot" title="RSM-21 ≥ 80 and rising over the last 3 sessions">🔥 HOT</span>; }

function IdxRow({ i }) {
  return (
    <div className={`mm-irow ${i.sub ? 'sub' : ''}`}>
      <span className="mm-iname">
        <span className="mm-iidx">{i.idx}{i.home && <span className="mm-home-dot" title="Home market"></span>}{i.hot && <HotBadge />}</span>
        {!i.sub && <span className="mm-ictry">{i.ctry}</span>}
      </span>
      <MiniHisto hist={i.rsm_hist} w={88} />
      <span className="mm-ilast mono">{mf0(i.last)}</span>
      <span className={`mm-ichg mono ${cls(i.chg)}`}>{pctTxt(i.chg)}</span>
    </div>
  );
}

/* ═══════════════════════ MACRO PAGE ═══════════════════════ */
/* `macro` comes from App's loadMacro() (null=loading, false=error) — same
 * data-flow convention as every other tab (screener, portfolio, backtest). */
function MacroPage({ macro: data }) {
  const [hovered, setHovered] = React.useState(null);

  if (data === null || data === undefined) return <div className="page"><div className="loading">Loading macro map…</div></div>;
  if (data === false || !data.indices?.length) return <div className="page"><div className="loading">Macro data unavailable.</div></div>;

  const indices = data.indices, commodities = data.commodities || [], crypto = data.crypto || [], fx = data.fx || [];
  const countryByIso = {};
  indices.forEach((i) => { if (!i.sub && !i.noMap && !countryByIso[i.iso]) countryByIso[i.iso] = i; });

  const mapped = indices.filter((i) => !i.sub);
  const up = mapped.filter((i) => i.chg > 0).length;
  const pctUp = mapped.length ? Math.round((up / mapped.length) * 100) : null;
  const riskOn = pctUp != null && pctUp >= 55;

  const findFx = (sym) => fx.find((f) => f.sym === sym);
  const findCommod = (name) => commodities.find((c) => c.name === name);
  const findCrypto = (sym) => crypto.find((c) => c.sym === sym);
  const home = countryByIso['764'];
  const dxy = findFx('DXY'), gold = findCommod('Gold'), btc = findCrypto('BTC');

  const GAUGES = [
    { l: 'Global Breadth', v: mapped.length ? `${up} / ${mapped.length}` : '—', c: mapped.length ? (riskOn ? 'up' : 'dn') : 'dm', sub: pctUp != null ? `${pctUp}% advancing` : '—' },
    { l: 'SET Index', v: home ? mf0(home.last) : '—', c: home ? cls(home.chg) : 'dm', sub: home ? pctTxt(home.chg) : '—' },
    { l: 'Dollar · DXY', v: dxy ? dxy.last.toFixed(2) : '—', c: dxy ? cls(dxy.chg) : 'dm', sub: dxy ? pctTxt(dxy.chg) : '—' },
    { l: 'Gold', v: gold ? '$' + mf0(gold.last) : '—', c: gold ? cls(gold.chg) : 'dm', sub: gold ? pctTxt(gold.chg) : '—' },
    { l: 'Bitcoin', v: btc ? '$' + mf0(btc.last) : '—', c: btc ? cls(btc.chg) : 'dm', sub: btc ? pctTxt(btc.chg) : '—' },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-t">Macro Map</h1>
          <p className="page-sub">Global markets snapshot · {new Date(data.generated_at).toLocaleString('en-GB', { timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} BKK · RSM-21 vs {data.benchmark}</p>
        </div>
      </div>

      <div className="mm-gauges">
        {GAUGES.map((g, i) => (
          <div key={i} className="mm-gauge">
            <div className="g-l">{g.l}</div>
            <div className="g-v mono">{g.v}</div>
            <div className={`g-c mono ${g.c}`}>{g.sub}</div>
          </div>
        ))}
      </div>

      <div className="mm-grid">
        <div className="mm-card mm-map-card">
          <div className="mm-card-head">
            <div>
              <div className="mm-card-t">World equities — momentum map</div>
              <div className="mm-card-sub">Shaded by RSM-21 vs {data.benchmark} · red weak → green strong · hover a market</div>
            </div>
          </div>
          <div className="mm-mapwrap">
            <WorldMap countryByIso={countryByIso} hovered={hovered} setHovered={setHovered} />
            <MapReadout countryByIso={countryByIso} hovered={hovered} />
          </div>
          <div className="mm-legend">
            <span>weak</span>
            <span className="mm-legbar"></span>
            <span>strong</span>
            <span className="mm-leg-sep">·</span>
            <span className="mm-leg-nd"></span>
            <span>not tracked</span>
          </div>
        </div>

        <div className="mm-card mm-idx-card">
          <div className="mm-card-head">
            <div className="mm-card-t">Major indices</div>
            <span className="mm-card-sub mono">{mapped.length} markets · bars = RSM-21</span>
          </div>
          <div className="mm-idx">
            {REGIONS.map((rg) => (
              <div key={rg}>
                <div className="mm-reg">{REGION_LABEL[rg]}</div>
                {indices.filter((i) => i.region === rg).map((i, k) => <IdxRow key={k} i={i} />)}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mm-bottom">
        <div className="mm-card">
          <div className="mm-card-head"><div className="mm-card-t">Commodities</div><span className="mm-card-sub mono">USD · RSM-21</span></div>
          {commodities.map((c, i) => (
            <div key={i} className="mm-brow">
              <span className="mm-bname">{c.name}<span className="mm-bunit">{c.unit}</span>{c.hot && <HotBadge />}</span>
              <MiniHisto hist={c.rsm_hist} w={72} h={20} />
              <span className="mm-blast mono">{mf2(c.last)}</span>
              <span className={`mm-bchg mono ${cls(c.chg)}`}>{pctTxt(c.chg, 1)}</span>
            </div>
          ))}
        </div>

        <div className="mm-card">
          <div className="mm-card-head"><div className="mm-card-t">Crypto</div><span className="mm-card-sub mono">24h · RSM-21</span></div>
          {crypto.map((c, i) => (
            <div key={i} className="mm-brow">
              <span className="mm-bname">{c.name}<span className="mm-bunit">{c.sym}</span>{c.hot && <HotBadge />}</span>
              <MiniHisto hist={c.rsm_hist} w={72} h={20} />
              <span className="mm-blast mono">{c.last >= 1000 ? mf0(c.last) : mf2(c.last)}</span>
              <span className={`mm-bchg mono ${cls(c.chg)}`}>{pctTxt(c.chg, 1)}</span>
            </div>
          ))}
        </div>

        <div className="mm-card">
          <div className="mm-card-head"><div className="mm-card-t">Currencies</div><span className="mm-card-sub mono">FX · RSM-21</span></div>
          {fx.map((f, i) => (
            <div key={i} className="mm-brow">
              <span className="mm-bname">{f.name}<span className="mm-bunit">{f.sym}</span>{f.hot && <HotBadge />}</span>
              <MiniHisto hist={f.rsm_hist} w={72} h={20} />
              <span className="mm-blast mono">{f.last.toFixed(f.dp ?? 2)}</span>
              <span className={`mm-bchg mono ${cls(f.chg)}`}>{pctTxt(f.chg, 1)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MacroPage });
