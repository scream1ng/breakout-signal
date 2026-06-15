/* bs-data.jsx — shared helpers only. No mock data. */

const fmt0 = (v) => v != null ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—';
const fmt1 = (v) => v != null ? Number(v).toFixed(1) : '—';
const fmt2 = (v) => v != null ? Number(v).toFixed(2) : '—';

const fmtDatetime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  } catch { return iso; }
};

const kindLabel = (row) => {
  const kind = String(row?.kind || '').toLowerCase();
  if (kind === 'tl') return row?.tl_angle != null ? `TL (${Number(row.tl_angle).toFixed(0)}°)` : 'TL';
  return 'Hz';
};

const tickerText = (item) => {
  const raw = typeof item === 'string' ? item : (item?.ticker_full || item?.ticker || item?.symbol || '');
  return String(raw || '').toUpperCase().replace(/^SET:/, '').replace(/\.BK$/, '');
};

const tickerFull = (item) => {
  const raw = typeof item === 'string' ? item : (item?.ticker || item?.symbol || '');
  const t = String(raw || '').toUpperCase();
  if (t.startsWith('^') || t.endsWith('.BK') || t.endsWith('.AX')) return t;
  return t + '.BK';
};

const CC = { Prime: 'P', RVOL: 'RV', RSM: 'RS', STR: 'ST', SMA50: 'S5' };

const bkkDateIso = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Bangkok' });

const isMarketOpenOrLater = () => {
  const bkk = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Bangkok' }));
  return bkk.getHours() * 60 + bkk.getMinutes() >= 600;
};

Object.assign(window, {
  BS: { fmt0, fmt1, fmt2, fmtDatetime, kindLabel, tickerText, tickerFull, CC, bkkDateIso, isMarketOpenOrLater }
});
