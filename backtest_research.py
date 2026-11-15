"""
backtest_research.py — Honest, bias-reduced backtest of entry-rule variants.
============================================================================
Standalone research tool. Does NOT touch the dashboard backtest in main.py.

Differences from the dashboard backtest:
  • Universe = every SET stock passing price + turnover only
    (no "above SMA50 today" pre-screen, no "strong RSM today" pre-filter).
  • History = up to 3y daily (yfinance) — signals use only data up to each bar.
  • Compares entry-rule variants on identical signals with identical exits.

Variants:
  A  base      : current rules, fill at level + 1 tick (or open on gap)
  A2 base_late : current rules, fill at the break-day CLOSE (proxy for the
                 live 15-min scan buying after price already ran)
  B  no_chase  : A2, but skip unless close ≤ level + max_entry_ext_atr × ATR
  C  +market   : B + SET above its SMA50
  D  +trend    : C + stock SMA50 rising and price ≥ trend_near_high × 52w high
  E  dip       : C+D signals; buy the retest of the level within dip_max_bars,
                 stop just under the level (level − 1×ATR)
  F  combined  : D entries when not late, otherwise E dip entry
  G  stop order: standing order at level + 1 tick, fakeouts sold at close
  G2/G3        : G with the volume rule (final-day volume → upper bound) / + market
  V2 LIVE      : LIVE PAPER RULES — 15-min scan buys the break at market price
                 (RSM ≥ min, stretch ≤ 4, SET > rising SMA50, no volume rule), fakeouts held,
                 2×ATR stop, TP partials at +2/+4 ATR, exit on close < SMA50, no breakeven
  V2b          : same exits, but close-confirmed + buy next open (tested, not used)

Findings (Dec 2024 – Nov 2026, 190 stocks): A is look-ahead (knows the break
closed strong) — the dashboard backtest shares this flaw. Realistic entries
(A2, G, 15-min replay) are ≈ 0R with current exits. The market filter is the
most consistent effect; SMA50 trail beats EMA10 in up-markets but is streakier.

Known limits: delisted stocks are missing (current TradingView list); daily
bars can't show exactly when a 15-min scan fires (A2 is the pessimistic proxy).

Usage:
    .venv/bin/python backtest_research.py            # uses cached prices if present
    .venv/bin/python backtest_research.py --refresh  # re-download prices
"""

import argparse, os, sys, json
import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from config import CFG as BASE
from app.core.entry import detect_pivots
from app.core.rsm import calc_rsm_series
from app.core.exit import set_tick
from app.core.data import load_benchmark

CACHE = os.path.join(ROOT, 'data', 'research_prices.pkl')

CFG = dict(
    rsm_min=BASE.get('rs_momentum_min', 80), rvol_min=BASE.get('rvol_min', 2.0),
    rvol_period=BASE.get('rvol_period', 20), psth_fast=BASE.get('psth_fast', 3),
    psth_slow=BASE.get('psth_slow', 9), sl_mult=BASE.get('sl_atr_mult', 1),
    tp1_mult=BASE.get('tp1_atr_mult', 2), tp2_mult=BASE.get('tp2_atr_mult', 4),
    be_days=BASE.get('be_after_days', 3), commission=BASE.get('commission', 0.0015),
    max_ext=BASE.get('max_entry_ext_atr', 0.25), near_high=BASE.get('trend_near_high', 0.90),
    dip_bars=BASE.get('dip_max_bars', 10), dip_band=BASE.get('dip_band_atr', 0.25),
)


# ── Data ──────────────────────────────────────────────────────────────────────

def fetch_universe():
    """All SET common stocks with price ≥ min_price and turnover ≥ min_turnover."""
    payload = {
        'filter': [{'left': 'type', 'operation': 'equal', 'right': 'stock'}],
        'columns': ['name', 'close', 'average_volume_10d_calc'],
        'range': [0, 3000],
    }
    r = requests.post('https://scanner.tradingview.com/thailand/scan', json=payload, timeout=30)
    r.raise_for_status()
    out = []
    for it in r.json().get('data', []):
        name, price, vol = it['d'][0], it['d'][1] or 0, it['d'][2] or 0
        if any(x in name for x in ['.F', '.R', '-W', '-R']):
            continue
        if price >= BASE.get('min_price', 0.5) and price * vol >= BASE['min_turnover']:
            out.append(f'{name}.BK')
    return sorted(out)


def load_prices(refresh=False):
    if not refresh and os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    tickers = fetch_universe()
    print(f'  Universe: {len(tickers)} stocks — downloading 3y daily...')
    out = {}
    for k in range(0, len(tickers), 100):
        chunk = tickers[k:k + 100]
        raw = yf.download(chunk, period='3y', interval='1d', auto_adjust=True,
                          progress=False, group_by='ticker', threads=True)
        for t in chunk:
            try:
                df = raw[t].dropna()
                if len(df) >= 260:
                    out[t] = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            except Exception:
                pass
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pd.to_pickle(out, CACHE)
    return out


def prep(df, bench):
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    c = df['Close']
    b = bench.reindex(df.index, method='ffill')
    df['RSM'] = calc_rsm_series(c.values, b.values)
    df['EMA10'] = c.ewm(span=10, adjust=False).mean()
    df['EMA20'] = c.ewm(span=20, adjust=False).mean()
    df['SMA50'] = c.rolling(50).mean()
    tr = pd.concat([df.High - df.Low, (df.High - c.shift()).abs(), (df.Low - c.shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    df['HI252'] = df.High.rolling(252, min_periods=120).max()
    b50 = b.rolling(50).mean()
    df['SET_OK'] = ((b > b50) & (b50 > b50.shift(20))).values   # SET above a RISING SMA50
    df['SET_OK'] = df['SET_OK'] & b.notna().values
    return df


# ── Simulation (mirrors app/core/exit.py rules) ───────────────────────────────

def manage(df, i0, ep, sl, atr):
    """Hold from bar i0 (entry bar). Exits checked from i0+1. Returns (R, ret%, bars)."""
    com = CFG['commission']
    sld = ep - sl
    if sld <= 0:
        return None
    tp1, tp2 = ep + CFG['tp1_mult'] * atr, ep + CFG['tp2_mult'] * atr
    rem, real, tp1h, tp2h = 1.0, -ep * com, False, False
    N = len(df)
    for j in range(i0 + 1, N):
        c = float(df.Close.iat[j]); e10 = float(df.EMA10.iat[j])
        if j - i0 == CFG['be_days']:
            sl = max(sl, ep)
        if not tp1h and c >= tp1:
            real += 0.3 * (tp1 - ep) - 0.3 * tp1 * com; rem = 0.7; tp1h = True
        if tp1h and not tp2h and c >= tp2:
            sh = rem * (0.3 / 0.7)
            real += sh * (tp2 - ep) - sh * tp2 * com; rem -= sh; tp2h = True
        if c <= sl or c < e10:
            real += rem * (c - ep) - rem * c * com
            return real / sld, real / ep * 100, j - i0
    c = float(df.Close.iat[-1])
    real += rem * (c - ep) - rem * c * com
    return real / sld, real / ep * 100, N - 1 - i0


def manage_v2(df, i0, ep, atr):
    """Paper v2 exits: SL entry − 2×ATR, TP1/TP2 partial at +2/+4 ATR, no BE, trail close < SMA50."""
    com = CFG['commission']
    sld = BASE.get('paper_sl_atr_mult', 2) * atr
    sl, tp1, tp2 = ep - sld, ep + CFG['tp1_mult'] * atr, ep + CFG['tp2_mult'] * atr
    trail = BASE.get('paper_trail', 'SMA50')
    if trail not in df.columns:
        n = int(trail[3:])
        df[trail] = (df.Close.ewm(span=n, adjust=False).mean() if trail.startswith('EMA')
                     else df.Close.rolling(n).mean())
    rem, real, tp1h, tp2h = 1.0, -ep * com, False, False
    for j in range(i0 + 1, len(df)):
        c = float(df.Close.iat[j])
        if not tp1h and c >= tp1:
            real += 0.3 * (tp1 - ep) - 0.3 * tp1 * com; rem = 0.7; tp1h = True
        if tp1h and not tp2h and c >= tp2:
            sh = rem * (0.3 / 0.7); real += sh * (tp2 - ep) - sh * tp2 * com; rem -= sh; tp2h = True
        if c <= sl or c < float(df[trail].iat[j]):
            real += rem * (c - ep) - rem * c * com
            return real / sld, real / ep * 100, j - i0
    c = float(df.Close.iat[-1]); real += rem * (c - ep) - rem * c * com
    return real / sld, real / ep * 100, len(df) - 1 - i0


def signals_for(df):
    cl = df['Close']
    avg_vol = df['Volume'].rolling(CFG['rvol_period'], min_periods=1).mean().values
    rvol = np.where(avg_vol > 0, df['Volume'].values / avg_vol, 0.0)
    b3, hz3, tl3, _ = detect_pivots(df, CFG['psth_fast'], rvol, CFG)
    b9, hz9, tl9, _ = detect_pivots(df, CFG['psth_slow'], rvol, CFG)
    m = {}
    for b in b3 + b9:
        m[b['bar']] = b
    sigs = [b for b in sorted(m.values(), key=lambda x: x['bar'])
            if b['rsm_ok'] and b['rvol_ok'] and b['regime_ok'] and b.get('stretch', 0) <= 4]
    return sigs, hz3 + hz9 + tl3 + tl9


def stop_order_trades(t, df, lines, start_i):
    """
    G: standing buy-stop at level + 1 tick on every active line, placed only when
    the stock was eligible at the PRIOR close (RSM ≥ min, close > SMA50). No volume
    check (unknowable when the order fills). First touch per line only.
    Fakeout (close ≤ level on fill day) → sold at that close, like the 16:25 review.
    """
    rows, seen, fills = [], set(), set()
    avg_vol = df['Volume'].rolling(CFG['rvol_period'], min_periods=1).mean()
    for xs, ys in lines:
        for x, y in zip(xs, ys):
            if x < start_i or x >= len(df) - 1 or x < 1:
                continue
            key = round(float(y), 4) if xs is not None else None
            p = x - 1
            if not (df.RSM.iat[p] >= CFG['rsm_min'] and df.Close.iat[p] > df.SMA50.iat[p]):
                continue
            if df.Close.iat[p] > y:      # already above → not a fresh break
                continue
            trig = y + set_tick(y)
            if df.High.iat[x] < trig:
                continue
            if (id(xs), ) in seen:
                break
            seen.add((id(xs), ))
            fk = (x, round(float(y), 4))          # fast/slow pivots often share a level
            if fk in fills:
                break
            fills.add(fk)
            atr = float(df.ATR.iat[x])
            if not atr or np.isnan(atr):
                break
            ep = max(trig, float(df.Open.iat[x]))
            c = float(df.Close.iat[x])
            date = str(df.index[x].date())
            if c <= y:   # fakeout — exit at close
                com = CFG['commission']
                pnl = (c - ep) - (ep + c) * com
                res = (pnl / atr, pnl / ep * 100, 0)
            else:
                res = manage(df, x, ep, ep - atr, atr)
            if res:
                base = dict(ticker=t, date=date, R=res[0], ret=res[1], bars=res[2], ext=np.nan,
                            set_ok=bool(df.SET_OK.iat[p]), trend_ok=None)
                rows.append(dict(base, variant='G  stop order at level'))
                # G2: same, but keep the Prime volume + stretch rules using the final day's
                # volume (optimistic stand-in for projected RVol → upper bound)
                rv = df.Volume.iat[x] / avg_vol.iat[x] if avg_vol.iat[x] > 0 else 0
                sma = df.SMA50.iat[x]
                stretch = ((y - sma) / sma * 100) / (atr / y * 100) if sma > 0 else 0
                if rv >= CFG['rvol_min'] and stretch <= 4:
                    rows.append(dict(base, variant='G2 stop order + volume rule'))
                    if base['set_ok']:
                        rows.append(dict(base, variant='G3 G2 + market filter'))
            # V2 LIVE RULES: 15-min scan buys the break at market price (modelled as the
            # midpoint between the line and the close), SET up, not overextended,
            # no volume rule, fakeouts held, v2 exits.
            sma_p, atr_p = df.SMA50.iat[p], float(df.ATR.iat[p])
            stretch_p = ((y - sma_p) / sma_p * 100) / (atr_p / y * 100) if sma_p > 0 and atr_p > 0 else 99
            if df.SET_OK.iat[p] and stretch_p <= 4 and atr_p > 0:
                ep_mid = max(ep, (trig + max(c, trig)) / 2)
                r = manage_v2(df, x, ep_mid, atr_p)
                if r:
                    rows.append(dict(ticker=t, date=date, R=r[0], ret=r[1], bars=r[2], ext=np.nan,
                                     set_ok=True, trend_ok=None, variant='V2 LIVE: buy break, mkt up, SMA50 exit'))
            break
    return rows


def run_ticker(t, df, start_i):
    rows = []
    sigs, lines = signals_for(df)
    rows += stop_order_trades(t, df, lines, start_i)
    for b in sigs:
        i, lv = b['bar'], float(b['bp'])
        if i < start_i or i >= len(df) - 1:
            continue
        atr = float(df.ATR.iat[i])
        if not atr or np.isnan(atr):
            continue
        o, c = float(df.Open.iat[i]), float(df.Close.iat[i])
        ext = (c - lv) / atr
        set_ok = bool(df.SET_OK.iat[i - 1])
        sma_up = df.SMA50.iat[i - 1] > df.SMA50.iat[i - 21]
        near_hi = c >= CFG['near_high'] * float(df.HI252.iat[i - 1]) if not np.isnan(df.HI252.iat[i - 1]) else False
        trend_ok = bool(sma_up and near_hi)
        base = dict(ticker=t, date=str(df.index[i].date()), ext=ext, set_ok=set_ok, trend_ok=trend_ok)

        def add(variant, res):
            if res:
                rows.append(dict(base, variant=variant, R=res[0], ret=res[1], bars=res[2]))

        # V2 (live paper rules): confirmed at close, SET up, buy next open, v2 exits
        if set_ok:
            add('V2b next-open variant (not used)', manage_v2(df, i + 1, float(df.Open.iat[i + 1]), atr))
            add('V2b next-open, current exits', manage(df, i + 1, float(df.Open.iat[i + 1]),
                                                    float(df.Open.iat[i + 1]) - atr, atr))

        ep_a = max(lv + set_tick(lv), o)
        add('A  base (fill at level)', manage(df, i, ep_a, ep_a - atr, atr))
        add('A2 base, buy late (close)', manage(df, i, c, c - atr, atr))
        late = ext > CFG['max_ext']
        if not late:
            add('B  no chase', manage(df, i, c, c - atr, atr))
            if set_ok:
                add('C  + market filter', manage(df, i, c, c - atr, atr))
                if trend_ok:
                    add('D  + trend filter', manage(df, i, c, c - atr, atr))
                    add('F  no-chase or dip', manage(df, i, c, c - atr, atr))

        # Dip entry: wait for retest of level within dip_bars after the break
        if set_ok and trend_ok:
            band = lv + CFG['dip_band'] * atr
            stop = lv - CFG['sl_mult'] * atr
            for j in range(i + 1, min(i + 1 + CFG['dip_bars'], len(df) - 1)):
                if float(df.Close.iat[j]) <= stop:
                    break
                if float(df.Low.iat[j]) <= band:
                    ep = min(float(df.Open.iat[j]), band)
                    if ep <= stop:
                        break
                    res = manage(df, j, ep, stop, atr)
                    add('E  dip entry', res)
                    if late:
                        add('F  no-chase or dip', res)
                    break
    return rows


def summarize(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        print('no trades'); return df
    out = []
    for v, g in df.sort_values('date').groupby('variant'):
        eq = g.R.cumsum()
        dd = (eq - eq.cummax()).min()
        out.append(dict(variant=v, trades=len(g), win=(g.R > 0).mean() * 100,
                        avg_R=g.R.mean(), total_R=g.R.sum(), avg_ret=g.ret.mean(),
                        max_dd_R=dd, early_exit=(g.bars <= 2).mean() * 100))
    s = pd.DataFrame(out).set_index('variant')
    pd.set_option('display.width', 160)
    print('\n  R = profit in units of risk (1R = the stop distance). Positive avg_R = system makes money.')
    print(s.round(2).to_string())
    df['year'] = df.date.str[:4]
    print('\n  avg_R by year')
    print(df.pivot_table(index='variant', columns='year', values='R', aggfunc='mean').round(2).to_string())
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'research_trades.csv'))
    a = ap.parse_args()

    bench = load_benchmark({'benchmark': '^SET.BK'})
    if bench is None or len(bench) < 100:
        sys.exit('  Could not load SET index (needs SETTRADE credentials).')
    bench.index = pd.to_datetime(bench.index).normalize()
    bench = bench[~bench.index.duplicated()]
    start = bench.index[60]   # need SET SMA50 history before the first test bar
    print(f'  SET index {bench.index[0].date()} → {bench.index[-1].date()}; testing from {start.date()}')

    prices = load_prices(a.refresh)
    rows = []
    for k, (t, raw) in enumerate(prices.items()):
        df = prep(raw, bench)
        start_i = max(int(df.index.searchsorted(start)), 260)
        if start_i >= len(df) - 5:
            continue
        try:
            rows += run_ticker(t, df, start_i)
        except Exception as e:
            print(f'  [skip] {t}: {e}')
        if (k + 1) % 100 == 0:
            print(f'  {k + 1}/{len(prices)} stocks...')
    df = summarize(rows)
    if not df.empty:
        df.to_csv(a.out, index=False)
        print(f'\n  Trades → {a.out}')


if __name__ == '__main__':
    main()
