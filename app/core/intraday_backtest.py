"""
intraday_backtest.py
Separate intraday backtest:
- watchlist built from prior EOD daily data
- entry on 15-minute decision closes
- projected volume filter at entry time
- fakeout exit if last 10 minutes close back below level
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

import numpy as np
import pandas as pd
import pytz

from app.core.data import load_benchmark, load_intraday_ticker, load_ticker
from app.core.entry import detect_pivots
from app.core.rsm import calc_rsm_series
from app.core.watchlist import merge_pending_levels


BKK = pytz.timezone('Asia/Bangkok')
_OPEN_MIN = 10 * 60
_LUNCH_S = 12 * 60 + 30
_LUNCH_E = 14 * 60
_CLOSE_MIN = 16 * 60 + 30
_TOTAL_MIN = 300


@dataclass
class _WatchLevel:
    level: float
    kind: str
    tl_angle: float | None
    stretch: float
    rsm: float
    atr: float
    avg_volume: float
    criteria: str


def _cfg_val(cfg: dict, name: str, fallback: str):
    return cfg.get(name, cfg.get(fallback))


def _criteria_label(rsm: float, proj_rvol: float, stretch: float, cfg: dict) -> str:
    rvol_ok = proj_rvol >= float(cfg.get('rvol_min', 2.0))
    rsm_ok = rsm >= float(cfg.get('rs_momentum_min', cfg.get('rsm_min', 80)))
    if stretch > 4:
        return 'STR'
    if rvol_ok and rsm_ok:
        return 'Prime'
    if rvol_ok:
        return 'RVOL'
    if rsm_ok:
        return 'RSM'
    return 'SMA50'


def _normalize_intraday(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, 'tz', None) is None:
        idx = idx.tz_localize(BKK)
    else:
        idx = idx.tz_convert(BKK)
    # Treat timestamps as bar starts so scan/fakeout logic works off bar closes.
    out.index = idx + pd.Timedelta(minutes=5)
    return out.sort_index()


def _elapsed_minutes(ts: pd.Timestamp) -> int:
    now_min = ts.hour * 60 + ts.minute
    if now_min <= _LUNCH_S:
        elapsed = max(now_min - _OPEN_MIN, 1)
    elif now_min < _LUNCH_E:
        elapsed = 150
    else:
        elapsed = 150 + max(now_min - _LUNCH_E, 1)
    return min(max(elapsed, 1), _TOTAL_MIN)


def _projected_rvol(cum_volume: float, avg_volume: float, ts: pd.Timestamp) -> float:
    if avg_volume <= 0:
        return 0.0
    return round(cum_volume * _TOTAL_MIN / _elapsed_minutes(ts) / avg_volume, 2)


def _is_scan_bar(ts: pd.Timestamp) -> bool:
    mins = ts.hour * 60 + ts.minute
    return ts.minute % 15 == 0 and (
        (10 * 60 + 15) <= mins <= (12 * 60 + 30)
        or (14 * 60) <= mins <= (16 * 60 + 15)
    )


def _is_fakeout_bar(ts: pd.Timestamp) -> bool:
    mins = ts.hour * 60 + ts.minute
    return (16 * 60 + 25) <= mins <= _CLOSE_MIN


def _prepare_daily_frame(ticker: str, cfg: dict, bench: pd.Series | None) -> pd.DataFrame | None:
    period = cfg.get('period', '12mo')
    df = load_ticker(ticker, period=period)
    if df is None or len(df) < 80 or bench is None:
        return None

    b_aligned = bench.reindex(df.index, method='ffill').values
    rsm_full = calc_rsm_series(df['Close'].values, b_aligned)
    if rsm_full is None:
        return None

    out = df.copy()
    out['RSM'] = rsm_full
    cl = out['Close']
    out['EMA10'] = cl.ewm(span=10, adjust=False).mean()
    out['EMA20'] = cl.ewm(span=20, adjust=False).mean()
    out['SMA50'] = cl.rolling(50).mean()
    out['SMA200'] = cl.rolling(200).mean()
    hl = out['High'] - out['Low']
    hpc = (out['High'] - out['Close'].shift()).abs()
    lpc = (out['Low'] - out['Close'].shift()).abs()
    out['ATR'] = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(14).mean()
    out['AVG_VOL20'] = out['Volume'].rolling(20, min_periods=1).mean()
    return out.dropna(subset=['EMA10', 'EMA20', 'SMA50', 'ATR'])


def _build_watch_levels(df_hist: pd.DataFrame, ticker: str, cfg: dict) -> list[_WatchLevel]:
    if df_hist is None or len(df_hist) < 60:
        return []

    avg_vol = df_hist['AVG_VOL20'].values
    rvol_arr = np.where(avg_vol > 0, df_hist['Volume'].values / avg_vol, 0.0)

    _, _, _, pend_fast = detect_pivots(df_hist, int(cfg['psth_fast']), rvol_arr, cfg, ticker)
    _, _, _, pend_slow = detect_pivots(df_hist, int(cfg['psth_slow']), rvol_arr, cfg, ticker)
    pending = merge_pending_levels(pend_fast, pend_slow)
    if not pending:
        return []

    last = df_hist.iloc[-1]
    last_close = float(last['Close'])
    last_sma50 = float(last['SMA50']) if not pd.isna(last['SMA50']) else 0.0
    if last_sma50 <= 0 or last_close <= last_sma50:
        return []

    last_atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0.0
    last_rsm = float(last['RSM']) if not pd.isna(last['RSM']) else 0.0
    last_avg_vol = float(last['AVG_VOL20']) if not pd.isna(last['AVG_VOL20']) else 0.0

    rows: list[_WatchLevel] = []
    for level in sorted(pending, key=lambda x: float(x.get('level', 0) or 0)):
        price = float(level.get('level', 0) or 0)
        if price <= 0 or last_atr <= 0:
            continue
        atr_pct = (last_atr / price * 100) if price > 0 else 0.0
        dist_pct = ((price - last_sma50) / last_sma50 * 100) if last_sma50 > 0 else 0.0
        stretch = round(dist_pct / atr_pct, 2) if atr_pct > 0 else 0.0
        rows.append(_WatchLevel(
            level=round(price, 4),
            kind=str(level.get('kind', '')).lower(),
            tl_angle=level.get('tl_angle'),
            stretch=stretch,
            rsm=round(last_rsm, 1),
            atr=round(last_atr, 4),
            avg_volume=last_avg_vol,
            criteria='',
        ))
    return rows


def _close_trade(pos: dict, price: float, when: pd.Timestamp, reason: str, capital: float) -> dict:
    commission = float(pos['commission'])
    realized = float(pos['realized_pnl'])
    remaining = float(pos['shares_remaining'])
    entry = float(pos['entry_price'])
    if remaining > 0:
        realized += ((price - entry) * remaining - price * remaining * commission)
    invested = entry * float(pos['shares'])
    total_pnl = realized
    return dict(
        ticker=pos['ticker'],
        entry_date=pos['entry_date'],
        exit_date=str(when.date()),
        entry_time=pos['entry_time'],
        exit_time=when.isoformat(timespec='seconds'),
        filter_type=pos['filter_type'],
        entry_price=round(entry, 4),
        exit_price=round(price, 4),
        entry_level=round(float(pos['entry_level']), 4),
        atr_val=round(float(pos['atr']), 4),
        tp1_hit=bool(pos['tp1_hit']),
        tp2_hit=bool(pos['tp2_hit']),
        win=total_pnl > 0,
        exit_reason=reason,
        total_pnl=round(total_pnl, 2),
        pnl_pct=round(total_pnl / capital * 100, 4) if capital > 0 else 0.0,
        ret_pct=round(total_pnl / invested * 100, 4) if invested > 0 else 0.0,
        entry_return_pct=round(total_pnl / invested * 100, 4) if invested > 0 else 0.0,
        stretch=round(float(pos['stretch']), 2),
    )


def _manage_position(
    pos: dict,
    close: float,
    when: pd.Timestamp,
    ema10_val: float | None,
    be_days: int,
    capital: float,
) -> tuple[dict | None, dict | None]:
    opened_date = Date.fromisoformat(pos['entry_date'])
    days_held = (when.date() - opened_date).days
    entry = float(pos['entry_price'])
    commission = float(pos['commission'])

    if days_held >= be_days and float(pos['sl']) < entry:
        pos['sl'] = entry

    if (not pos['tp1_hit']) and close >= float(pos['tp1']):
        sh = float(pos['shares']) * 0.30
        pos['realized_pnl'] += ((float(pos['tp1']) - entry) * sh - float(pos['tp1']) * sh * commission)
        pos['shares_remaining'] = float(pos['shares']) * 0.70
        pos['tp1_hit'] = True

    if pos['tp1_hit'] and (not pos['tp2_hit']) and close >= float(pos['tp2']):
        frac = 0.30 / 0.70
        sh = float(pos['shares_remaining']) * frac
        pos['realized_pnl'] += ((float(pos['tp2']) - entry) * sh - float(pos['tp2']) * sh * commission)
        pos['shares_remaining'] *= (1 - frac)
        pos['tp2_hit'] = True

    sl_hit = close <= float(pos['sl'])
    ema_hit = ema10_val is not None and close < ema10_val
    if sl_hit or ema_hit:
        reason = 'EMA10' if (ema_hit and not sl_hit) else ('BE' if abs(float(pos['sl']) - entry) < 1e-9 else 'SL')
        trade = _close_trade(pos, close, when, reason, capital)
        return None, trade

    return pos, None


def _summarize_mode(stock_rows: list[dict], capital: float) -> dict | None:
    if not stock_rows:
        return None

    all_prime = [t for row in stock_rows for t in row.get('trades_all', []) if t.get('filter_type') == 'Prime']
    wins = [t for t in all_prime if t.get('win')]
    losses = [t for t in all_prime if not t.get('win')]
    return dict(
        n_trades=len(all_prime),
        wr=round(len(wins) / len(all_prime) * 100, 1) if all_prime else 0.0,
        pnl_pct=round(sum(row.get('total_pnl_pct', 0) for row in stock_rows), 2),
        avg_win=round(sum(t.get('ret_pct', 0) for t in wins) / len(wins), 2) if wins else 0.0,
        avg_loss=round(sum(t.get('ret_pct', 0) for t in losses) / len(losses), 2) if losses else 0.0,
        n_stocks=len(stock_rows),
        capital=capital,
        note='15m close entry, 5m last-10m fakeout, 60d intraday window',
    )


def _row_from_trades(meta: dict, trades: list[dict], capital: float) -> dict:
    by_type: dict[str, dict] = {}
    for ft in ('Prime', 'RVOL'):
        ts = [t for t in trades if t.get('filter_type') == ft]
        if not ts:
            continue
        wins = [t for t in ts if t.get('win')]
        losses = [t for t in ts if not t.get('win')]
        by_type[ft] = dict(
            n=len(ts),
            wr=round(len(wins) / len(ts) * 100, 1) if ts else 0.0,
            avg_win=round(sum(t.get('ret_pct', 0) for t in wins) / len(wins), 2) if wins else None,
            avg_loss=round(sum(t.get('ret_pct', 0) for t in losses) / len(losses), 2) if losses else None,
            pnl_capital=round(sum(t.get('pnl_pct', 0) for t in ts), 2),
        )

    prime = [t for t in trades if t.get('filter_type') == 'Prime']
    prime_wins = [t for t in prime if t.get('win')]
    total_pnl = sum(t.get('total_pnl', 0) for t in prime)
    return dict(
        ticker=meta['ticker'].replace('.BK', '').replace('.AX', ''),
        sector=meta.get('sector', ''),
        trades=len(prime),
        wr=round(len(prime_wins) / len(prime) * 100, 1) if prime else 0.0,
        pnl_pct=round(total_pnl / capital * 100, 2) if capital > 0 else 0.0,
        rsm=round(meta.get('rs_momentum', 0), 1),
        has_signal=bool(meta.get('today_signal')),
        has_pending=bool(meta.get('pending')),
        by_type=by_type,
        trades_all=trades,
        total_pnl_pct=round(total_pnl / capital * 100, 4) if capital > 0 else 0.0,
    )


def simulate_stock_intraday(meta: dict, cfg: dict, bench: pd.Series | None) -> dict | None:
    ticker = meta['ticker']
    daily_df = _prepare_daily_frame(ticker, cfg, bench)
    intraday_df = _normalize_intraday(load_intraday_ticker(ticker, period='60d', interval='5m'))
    if daily_df is None or intraday_df is None or intraday_df.empty:
        return None

    capital = float(cfg.get('capital', 100_000))
    risk_pct = float(cfg.get('risk_pct', 0.005))
    commission = float(cfg.get('commission', 0.0015))
    sl_mult = float(_cfg_val(cfg, 'sl_mult', 'sl_atr_mult') or 1)
    tp1_mult = float(_cfg_val(cfg, 'tp1_mult', 'tp1_atr_mult') or 2)
    tp2_mult = float(_cfg_val(cfg, 'tp2_mult', 'tp2_atr_mult') or 4)
    be_days = int(_cfg_val(cfg, 'be_days', 'be_after_days') or 3)

    daily_dates = {d.date(): i for i, d in enumerate(daily_df.index)}
    session_dates = sorted({ts.date() for ts in intraday_df.index if ts.date() in daily_dates})
    trades: list[dict] = []
    pos: dict | None = None

    for session_date in session_dates:
        day_idx = daily_dates.get(session_date)
        if day_idx is None or day_idx < 1:
            continue

        day_5m = intraday_df[intraday_df.index.date == session_date]
        if day_5m.empty:
            continue

        ema10_prev = daily_df['EMA10'].iloc[day_idx - 1]
        ema10_val = float(ema10_prev) if not pd.isna(ema10_prev) else None

        entered_today = False
        watch_levels: list[_WatchLevel] = []
        if pos is None:
            watch_levels = _build_watch_levels(daily_df.iloc[:day_idx].copy(), ticker, cfg)

        scan_bars = day_5m[[ _is_scan_bar(ts) for ts in day_5m.index ]]
        for ts, bar in scan_bars.iterrows():
            close = float(bar['Close'])

            if pos is not None and pos.get('entry_time') != ts.isoformat(timespec='seconds'):
                pos, trade = _manage_position(pos, close, ts, ema10_val, be_days, capital)
                if trade:
                    trades.append(trade)
                    entered_today = True
                    continue

            if pos is not None or entered_today:
                continue

            cum_vol = float(day_5m.loc[:ts, 'Volume'].sum())
            triggered = []
            for row in watch_levels:
                if close <= row.level:
                    continue
                proj_rvol = _projected_rvol(cum_vol, row.avg_volume, ts)
                crit = _criteria_label(row.rsm, proj_rvol, row.stretch, cfg)
                if crit in ('Prime', 'RVOL'):
                    triggered.append((row.level, row, crit))

            if not triggered:
                continue

            level, watch, crit = sorted(triggered, key=lambda x: x[0])[0]
            stop_distance = float(watch.atr) * sl_mult
            if stop_distance <= 0:
                continue
            shares = max(1, int((capital * risk_pct) / stop_distance))
            pos = dict(
                ticker=ticker,
                filter_type=crit,
                entry_price=close,
                entry_level=level,
                entry_date=str(session_date),
                entry_time=ts.isoformat(timespec='seconds'),
                shares=shares,
                shares_remaining=float(shares),
                atr=watch.atr,
                sl=close - stop_distance,
                tp1=close + tp1_mult * stop_distance,
                tp2=close + tp2_mult * stop_distance,
                tp1_hit=False,
                tp2_hit=False,
                realized_pnl=-(close * shares * commission),
                commission=commission,
                stretch=watch.stretch,
            )
            entered_today = True

        if pos is None:
            continue

        if pos['entry_date'] == str(session_date):
            fakeout_bars = day_5m[[ _is_fakeout_bar(ts) for ts in day_5m.index ]]
            for ts, bar in fakeout_bars.iterrows():
                if float(bar['Close']) < float(pos['entry_level']):
                    trades.append(_close_trade(pos, float(bar['Close']), ts, 'FALSE_BREAKOUT', capital))
                    pos = None
                    break

    if pos is not None:
        last_ts = intraday_df.index[-1]
        last_close = float(intraday_df['Close'].iloc[-1])
        trades.append(_close_trade(pos, last_close, last_ts, 'End', capital))

    return _row_from_trades(meta, trades, capital)


def build_intraday_backtest(results: list[dict], cfg: dict) -> dict | None:
    if not results:
        return None

    bench = load_benchmark(cfg)
    if bench is None:
        return None

    rows = []
    for meta in results:
        row = simulate_stock_intraday(meta, cfg, bench)
        if row:
            rows.append(row)

    if not rows:
        return None

    rows.sort(key=lambda x: x.get('pnl_pct', 0), reverse=True)
    overall = _summarize_mode(rows, float(cfg.get('capital', 100_000)))
    # Strip trade details before snapshot save.
    clean_rows = []
    for row in rows:
        clean = dict(row)
        clean.pop('trades_all', None)
        clean_rows.append(clean)

    return dict(
        overall_bt=overall,
        rows=clean_rows,
    )
