"""
intraday.py — Intraday watchlist scanner
=========================================
Loads watchlist.json, fetches today's data,
alerts if close > level. Projects morning session volume.

Usage:
    python intraday.py             # print only
    python intraday.py --discord   # send to Discord
"""

import os, sys, json, time, argparse, socket
socket.setdefaulttimeout(60)   # bound every network call so a stalled fetch can't hang the scan
from datetime import datetime
import pytz
import requests
import yfinance as yf
import pandas as pd

ROOT    = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from config import CFG
from app.scheduler.windows import is_allowed_intraday_scheduler_slot, scheduler_slot_label
from app.core.data import load_ticker, load_benchmark
from app.core.rsm import calc_live_rsm
from output.report import print_intraday
from output.notifications import send_intraday_alert, send_review_alert

BKK     = pytz.timezone('Asia/Bangkok')
WL_PATH = os.path.join(ROOT, 'data', 'watchlist.json')
STATE_PATH = os.path.join(ROOT, 'data', 'alert_state.json')

parser = argparse.ArgumentParser()
parser.add_argument('--discord', action='store_true')
parser.add_argument('--review', action='store_true')
args = parser.parse_args()


def _log(msg: str):
    stamp = datetime.now(BKK).strftime('%H:%M:%S')
    line = f'[{stamp}] {msg}'
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode('ascii', errors='replace').decode('ascii'), flush=True)


def _alert_key(ticker, level, kind=None):
    kind_part = str(kind or '').lower()
    return f'{ticker}|{kind_part}|{float(level):.4f}'


def _normalize_alert_state(saved: dict, date_str: str) -> dict:
    state = {'date': date_str, 'alerted': [], 'failed': []}
    if saved.get('date') != date_str:
        return state
    normalized = []
    for item in saved.get('alerted', []):
        if isinstance(item, dict):
            ticker = item.get('ticker')
            level = item.get('level')
            if ticker and level is not None:
                normalized.append(dict(
                    ticker=ticker,
                    sector=item.get('sector', ''),
                    level=float(level),
                    kind=item.get('kind', ''),
                    tl_angle=item.get('tl_angle'),
                    criteria=item.get('criteria', ''),
                    close=item.get('close'),
                    cur_rvol=item.get('cur_rvol'),
                    proj_rvol=item.get('proj_rvol'),
                    rsm=item.get('rsm'),
                    stretch=item.get('stretch'),
                    key=item.get('key') or _alert_key(ticker, level, item.get('kind')),
                    alerted_at=item.get('alerted_at'),
                ))
        elif isinstance(item, str):
            normalized.append(dict(ticker=item, level=None, kind='', key=item, alerted_at=None))
    failed = []
    for item in saved.get('failed', []):
        if isinstance(item, dict):
            ticker = item.get('ticker')
            level = item.get('level')
            if ticker and level is not None:
                failed.append(dict(
                    ticker=ticker,
                    level=float(level),
                    kind=item.get('kind', ''),
                    key=item.get('key') or _alert_key(ticker, level, item.get('kind')),
                    failed_at=item.get('failed_at'),
                    close=item.get('close'),
                ))
    state['alerted'] = normalized
    state['failed'] = failed
    return state


def _load_alert_state(date_str):
    state = {'date': date_str, 'alerted': [], 'failed': []}
    # DB first
    try:
        from app.storage.state import load_state as db_load
        saved = db_load(f'alert_state:{date_str}')
        if saved:
            return _normalize_alert_state(saved, date_str)
    except Exception:
        pass
    # JSON fallback
    if not os.path.exists(STATE_PATH):
        return state
    try:
        with open(STATE_PATH) as f:
            saved = json.load(f)
        return _normalize_alert_state(saved, date_str)
    except Exception:
        return state


def _save_alert_state(state):
    # DB first
    try:
        from app.storage.state import save_state
        save_state(f'alert_state:{state["date"]}', state)
    except Exception:
        pass
    # JSON always (local dev + legacy)
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def proj_volume(cur_volume, avg_volume, now):
    """Project full trading day RVol based on time elapsed.
    SET hours: 10:00-12:30 (150min) + 14:00-16:30 (150min) = 300min total.
    """
    if avg_volume <= 0:
        return 0.0
    open_min   = 10 * 60          # 10:00
    lunch_s    = 12 * 60 + 30     # 12:30
    lunch_e    = 14 * 60          # 14:00
    close_min  = 16 * 60 + 30     # 16:30
    total_min  = 300              # 150 + 150

    now_min = now.hour * 60 + now.minute

    if now_min <= lunch_s:
        # Morning session — elapsed since open
        elapsed = max(now_min - open_min, 1)
    elif now_min < lunch_e:
        # Lunch break — morning complete = 150min
        elapsed = 150
    else:
        # Afternoon session — add 150min morning + elapsed since 14:00
        elapsed = 150 + max(now_min - lunch_e, 1)

    elapsed   = min(elapsed, total_min)
    proj_vol  = cur_volume * total_min / elapsed
    return round(proj_vol / avg_volume, 2)


def fetch_today(ticker):
    try:
        df = yf.download(ticker, period='5d', interval='1d',
                         auto_adjust=True, progress=False)
        if df is None or len(df) == 0:
            return None
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        last = df.iloc[-1]
        return dict(close=float(last['Close']), volume=float(last['Volume']))
    except Exception as e:
        print(f'({e})', end=' ')
        return None


def criteria_label(rsm, rvol, stretch=0):
    rvol_ok = rvol >= CFG.get('rvol_min', 1.5)
    rsm_ok  = rsm  >= CFG.get('rs_momentum_min', 70)
    if stretch > 4: return 'STR'
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def _run_paper_update(signals, data, now):
    """Check paper exits for open positions; open new ones for Prime signals."""
    try:
        from app.core import paper_trader
        pt = paper_trader.load_trades()
        open_pos = list(pt.get('open', []))
        newly_closed = []

        if open_pos:
            exit_data = paper_trader.fetch_exit_data(open_pos)
            open_pos, newly_closed = paper_trader.check_exits(open_pos, exit_data, now, CFG)
            pt['closed'] = pt.get('closed', []) + newly_closed
            for p in newly_closed:
                sign = '+' if (p.get('total_pnl') or 0) >= 0 else ''
                _log(f'[paper] CLOSED {p["ticker"].replace(".BK","")} {p["exit_reason"]} '
                     f'pnl={sign}฿{(p.get("total_pnl") or 0):.0f}')

        prime = [s for s in (signals or []) if s.get('criteria') == 'Prime']
        opened = 0
        for sig in prime:
            trade, err = paper_trader.open_position(sig, CFG, now, open_pos)
            if trade:
                open_pos.append(trade)
                opened += 1
                tk = sig.get('ticker_full', sig.get('ticker', '?')).replace('.BK', '')
                _log(f'[paper] OPENED {tk} @ {trade["entry_price"]:.2f} × {trade["shares"]} '
                     f'SL={trade["sl"]:.2f} TP1={trade["tp1"]:.2f}')
            elif err:
                _log(f'[paper] skip — {err}')

        if newly_closed or opened:
            pt['open'] = open_pos
            paper_trader.save_trades(pt)
    except Exception as e:
        _log(f'[paper] error: {e}')


def _run_paper_fakeout(signals, data, now):
    """Exit paper positions that faked out (close < level at 16:25 review)."""
    try:
        from app.core import paper_trader
        pt = paper_trader.load_trades()
        open_pos = list(pt.get('open', []))
        if not open_pos:
            return
        fakeout_tickers = {s.get('ticker_full', s.get('ticker', '')) for s in signals}
        prices_map = {t: {'close': d['close']} for t, d in data.items()}
        still_open, newly_closed = paper_trader.fakeout_exits(open_pos, fakeout_tickers, prices_map, now, CFG)
        if newly_closed:
            pt['open'] = still_open
            pt['closed'] = pt.get('closed', []) + newly_closed
            paper_trader.save_trades(pt)
            for p in newly_closed:
                sign = '+' if (p.get('total_pnl') or 0) >= 0 else ''
                _log(f'[paper] FAKEOUT {p["ticker"].replace(".BK","")} '
                     f'pnl={sign}฿{(p.get("total_pnl") or 0):.0f}')
    except Exception as e:
        _log(f'[paper] fakeout error: {e}')


def build_live_rsm_map(tickers, data, now):
    """Recompute RS Momentum for each watchlist ticker using today's live price.

    The watchlist stores RSM frozen at the previous EOD scan; during the session
    a breakout stock's RSM can be materially different. We rebuild it from daily
    history (completed sessions only) plus the live close so intraday criteria
    match what the EOD scan would compute on the same move.

    Returns {ticker: rsm_float}. Tickers that can't be computed are omitted so
    callers fall back to the stored watchlist value.
    """
    rsm_map = {}
    try:
        bench = load_benchmark(CFG)
    except Exception as e:
        _log(f'[rsm] benchmark load failed ({e}) — using stored RSM')
        return rsm_map
    if bench is None or len(bench) < 21:
        _log('[rsm] benchmark unavailable — using stored RSM')
        return rsm_map

    today = pd.Timestamp(now.date())
    live_bench = float(bench.dropna().iloc[-1]) if len(bench.dropna()) else None

    computed = 0
    for ticker in tickers:
        d = data.get(ticker)
        if not d:
            continue
        try:
            df = load_ticker(ticker)
            if df is None or len(df) < 22:
                continue
            closes = df['Close']
            b_aligned = bench.reindex(closes.index, method='ffill')
            # Keep only completed sessions; the live close becomes the latest bar.
            completed = closes.index.normalize() < today
            closes = closes[completed]
            b_aligned = b_aligned[completed]
            if len(closes) < 21:
                continue
            rsm = calc_live_rsm(closes.values, b_aligned.values, d['close'], live_bench)
            if rsm > 0:
                rsm_map[ticker] = rsm
                computed += 1
        except Exception:
            continue

    if computed:
        _log(f'[rsm] recomputed live RSM for {computed}/{len(tickers)} stocks')
    return rsm_map


def run():
    now = datetime.now(BKK)
    date_str = now.strftime('%Y-%m-%d')

    if os.environ.get('ALERT_SOURCE', '').strip() == 'scheduler':
        if not is_allowed_intraday_scheduler_slot(now, review=args.review):
            slot = scheduler_slot_label(now)
            scan_kind = 'review' if args.review else 'intraday'
            _log(f'Scheduler {scan_kind} slot {slot} BKK is not allowed — skipping')
            return

    alert_state = _load_alert_state(date_str)
    alerted_keys = {item.get('key') for item in alert_state['alerted']}
    legacy_tickers = {item.get('ticker') for item in alert_state['alerted'] if item.get('level') is None}
    failed_keys = {item.get('key') for item in alert_state.get('failed', [])}

    # Load watchlist — DB first, JSON fallback
    watchlist = None
    try:
        from app.storage.state import load_state as db_load
        watchlist = db_load('watchlist')
    except Exception:
        pass
    if watchlist is None:
        if not os.path.exists(WL_PATH):
            _log('watchlist not found in DB or file — run main.py first')
            return
        with open(WL_PATH) as f:
            watchlist = json.load(f)

    if not watchlist:
        _log('Watchlist empty')
        return

    try:
        from app.core.settrade_client import get_market_data
        get_market_data()
        data_source = "SETTRADE OpenAPI"
    except Exception:
        data_source = "Yahoo Finance"

    tickers = list({w['ticker'] for w in watchlist})
    _log(f'Checking {len(tickers)} stocks ({data_source})')
    _log('Downloading prices...')
    data = {}
    use_yfinance = False
    
    try:
        from app.core.settrade_client import get_market_data
        market = get_market_data()
        for ticker in tickers:
            symbol = ticker.replace('.BK', '')
            try:
                quote = market.get_quote_symbol(symbol)
                last_price = quote.get('last') or quote.get('close') or quote.get('result', {}).get('last')
                vol = quote.get('totalVolume') or quote.get('volume') or quote.get('result', {}).get('totalVolume')
                if last_price:
                    data[ticker] = dict(close=float(last_price), volume=float(vol))
            except Exception:
                continue
        if not data:
            # If settrade connected but returned empty for all
            raise ValueError("No data returned from Settrade")
    except Exception as e:
        _log(f'Settrade unavailable → yfinance fallback')
        use_yfinance = True
        
    if use_yfinance:
        try:
            raw = yf.download(tickers, period='5d', interval='1d',
                              auto_adjust=True, progress=False, group_by='ticker')
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        df = raw
                    else:
                        df = raw[ticker]
                    if df is None or len(df) == 0:
                        continue
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0] for c in df.columns]
                    last = df.iloc[-1]
                    data[ticker] = dict(close=float(last['Close']), volume=float(last['Volume']))
                except Exception:
                    continue
        except Exception as e:
            _log(f'Download error: {e}')
            return

    # Recompute RSM live (watchlist value is frozen at the prior EOD scan).
    live_rsm = build_live_rsm_map(tickers, data, now)

    def rsm_for(ticker, w):
        """Live RSM when available, else the watchlist's stored EOD value."""
        return live_rsm.get(ticker, w.get('rsm', 0))

    no_data_tickers = []
    broke_tickers   = []
    live_data = {}
    for ticker in tickers:
        short   = ticker.replace('.BK', '')
        w_items = [w for w in watchlist if w['ticker'] == ticker]
        levels  = [w['level'] for w in w_items]
        d       = data.get(ticker)
        if not d:
            no_data_tickers.append(short)
            continue
        avg_vol  = w_items[0].get('avg_volume', 0) if w_items else 0
        proj_rv  = proj_volume(d['volume'], avg_vol, now) if avg_vol > 0 else 0.0
        rsm      = rsm_for(ticker, w_items[0]) if w_items else 0
        stretch  = w_items[0].get('stretch', 0) if w_items else 0
        broke    = any(d['close'] > lv for lv in levels)
        if broke:
            crit = criteria_label(rsm, proj_rv, stretch)
            _log(f'{short} → BREAK → {crit}  RVol {proj_rv:.1f}×  RSM {int(rsm)}')
            broke_tickers.append(short)
        live_data[ticker] = dict(close=round(float(d['close']), 4), rvol=proj_rv, broke=broke)

    below = len(tickers) - len(broke_tickers) - len(no_data_tickers)
    summary_parts = [f'{below} below level']
    if no_data_tickers:
        summary_parts.append(f'{len(no_data_tickers)} no data ({", ".join(no_data_tickers)})')
    _log(' | '.join(summary_parts))

    _live_path = os.path.join(ROOT, 'data', 'watchlist_live.json')
    try:
        with open(_live_path, 'w') as _lf:
            json.dump({'date': date_str, 'updated_at': now.isoformat(timespec='seconds'), 'prices': live_data}, _lf, indent=2)
        _log('Dashboard updated (watchlist_live.json)')
    except Exception as _e:
        _log(f'[warn] live price save failed: {_e}')

    signals = []
    seen    = set()
    for w in watchlist:
        ticker = w['ticker']
        level  = w['level']
        d      = data.get(ticker)
        if not d:
            continue
            
        key = (ticker, level)
        if key in seen:
            continue
        seen.add(key)

        if args.review:
            key_id = _alert_key(ticker, level, w.get('kind'))
            was_alerted = key_id in alerted_keys or ticker in legacy_tickers
            if was_alerted and d['close'] < level:
                avg_vol  = w.get('avg_volume', 0)
                cur_rvol = round(d['volume'] / avg_vol, 2) if avg_vol > 0 else 0
                proj_rv  = proj_volume(d['volume'], avg_vol, now)
                rsm      = rsm_for(ticker, w)
                stretch  = w.get('stretch', 0)
                crit     = criteria_label(rsm, proj_rv, stretch)
                signals.append(dict(
                    ticker    = ticker.replace('.BK', ''),
                    ticker_full = ticker,
                    level     = level,
                    close     = d['close'],
                    cur_rvol  = cur_rvol,
                    kind      = 'Hz' if w.get('kind') == 'hz' else 'TL',
                    rsm       = rsm,
                    stretch   = stretch,
                    criteria  = crit,
                    atr       = w.get('atr', 0),
                    tl_angle  = w.get('tl_angle')
                ))
                if key_id not in failed_keys:
                    alert_state.setdefault('failed', []).append(dict(
                        ticker=ticker,
                        sector=w.get('sector', ''),
                        level=float(level),
                        kind='Hz' if w.get('kind') == 'hz' else 'TL',
                        tl_angle=w.get('tl_angle'),
                        criteria=crit,
                        cur_rvol=cur_rvol,
                        proj_rvol=proj_rv,
                        rsm=rsm,
                        stretch=stretch,
                        key=key_id,
                        failed_at=now.isoformat(timespec='seconds'),
                        close=round(float(d['close']), 4),
                    ))
                    failed_keys.add(key_id)
            continue

        if d['close'] <= level:
            continue

        avg_vol  = w.get('avg_volume', 0)
        cur_rvol = round(d['volume'] / avg_vol, 2) if avg_vol > 0 else 0
        proj_rv  = proj_volume(d['volume'], avg_vol, now)
        rsm      = rsm_for(ticker, w)
        crit     = criteria_label(rsm, proj_rv, w.get('stretch', 0))

        if crit not in ('Prime', 'RVOL', 'STR'):
            continue

        key_id = _alert_key(ticker, level, w.get('kind'))
        if key_id in alerted_keys:
            continue

        alert_state['alerted'].append(dict(
            ticker=ticker,
            sector=w.get('sector', ''),
            level=float(level),
            kind='Hz' if w.get('kind') == 'hz' else 'TL',
            tl_angle=w.get('tl_angle'),
            criteria=crit,
            close=round(float(d['close']), 4),
            cur_rvol=cur_rvol,
            proj_rvol=proj_rv,
            rsm=rsm,
            stretch=w.get('stretch', 0),
            key=key_id,
            alerted_at=now.isoformat(timespec='seconds'),
        ))
        alerted_keys.add(key_id)

        signals.append(dict(
            ticker    = ticker.replace('.BK', ''),
            ticker_full = ticker,
            level     = level,
            close     = d['close'],
            cur_rvol  = cur_rvol,
            proj_rvol = proj_rv,
            kind      = 'Hz' if w.get('kind') == 'hz' else 'TL',
            rsm       = rsm,
            stretch   = w.get('stretch', 0),
            atr       = w.get('atr', 0),
            criteria  = crit,
            tl_angle  = w.get('tl_angle'),
        ))

    if args.review:
        if not signals:
            _log('No fakeouts. Done.')
            return
        _log(f'{len(signals)} fakeout(s): {", ".join(s["ticker"] for s in signals)}')
        _save_alert_state(alert_state)
        if args.discord:
            _log(f'Sending Discord → fakeout review')
            send_review_alert(signals, now, CFG)
        _run_paper_fakeout(signals, data, now)
        _log(f'Done. {len(signals)} fakeout(s)')
        return

    _run_paper_update(signals, data, now)

    if not signals:
        _log(f'No breakouts. Done.')
        return

    _save_alert_state(alert_state)
    print_intraday(signals, now.strftime('%Y-%m-%d'), now.strftime('%H:%M'))

    alert = signals

    if args.discord and alert:
        _log(f'Sending Discord → {len(alert)} break(s)')
        send_intraday_alert(alert, now, CFG)

    _log(f'Done. {len(signals)} break(s)')


if __name__ == '__main__':
    run()
    # Force clean termination — SETTRADE/other SDK clients can leave non-daemon
    # threads alive, hanging the interpreter after work completes and leaving
    # the scheduler JobRun stuck in 'running'. Flush streams, then hard-exit 0.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
