"""
core/paper_trade.py — Persistent paper-trade ledger.

Uses Railway Postgres automatically when DATABASE_URL is set.
Falls back to data/paper_portfolio.json for local use.
"""

import json
import os
from datetime import datetime

try:
    import psycopg2
except ImportError:
    psycopg2 = None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
STATE_PATH = os.path.join(DATA_DIR, 'paper_portfolio.json')
DB_URL = os.environ.get('DATABASE_URL', '').strip()


def _now_iso(now=None):
    stamp = now or datetime.utcnow()
    return stamp.isoformat(timespec='seconds')


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _db_enabled() -> bool:
    return bool(DB_URL and psycopg2 is not None)


def _db_connect():
    return psycopg2.connect(DB_URL)


def _db_init():
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists paper_trade_state (
                    state_key text primary key,
                    state_json text not null,
                    updated_at timestamptz not null default now()
                )
                """
            )


def _db_load_state(cfg: dict) -> dict:
    _db_init()
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select state_json from paper_trade_state where state_key = %s",
                ('default',),
            )
            row = cur.fetchone()

    if not row:
        return _initial_state(cfg)

    try:
        state = json.loads(row[0])
    except Exception:
        return _initial_state(cfg)

    baseline = _initial_state(cfg)
    baseline.update(state)
    baseline['capital'] = float(baseline.get('capital', cfg.get('capital', 100_000)))
    baseline['cash'] = float(baseline.get('cash', baseline['capital']))
    baseline['realized_pnl'] = float(baseline.get('realized_pnl', 0.0))
    baseline['next_id'] = int(baseline.get('next_id', 1))
    baseline['positions'] = list(baseline.get('positions', []))
    baseline['closed_positions'] = list(baseline.get('closed_positions', []))
    baseline['events'] = list(baseline.get('events', []))
    return baseline


def _db_save_state(state: dict, now=None) -> None:
    _db_init()
    state['updated_at'] = _now_iso(now)
    payload = json.dumps(state)
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into paper_trade_state (state_key, state_json, updated_at)
                values (%s, %s, now())
                on conflict (state_key) do update
                set state_json = excluded.state_json,
                    updated_at = now()
                """,
                ('default', payload),
            )


def _initial_state(cfg: dict) -> dict:
    capital = float(cfg.get('capital', 100_000))
    return dict(
        version=1,
        capital=capital,
        cash=capital,
        realized_pnl=0.0,
        next_id=1,
        positions=[],
        closed_positions=[],
        events=[],
        updated_at=_now_iso(),
    )


def load_state(cfg: dict) -> dict:
    if _db_enabled():
        return _db_load_state(cfg)

    _ensure_dir()
    if not os.path.exists(STATE_PATH):
        return _initial_state(cfg)
    try:
        with open(STATE_PATH, encoding='utf-8') as f:
            state = json.load(f)
    except Exception:
        return _initial_state(cfg)

    baseline = _initial_state(cfg)
    baseline.update(state)
    baseline['capital'] = float(baseline.get('capital', cfg.get('capital', 100_000)))
    baseline['cash'] = float(baseline.get('cash', baseline['capital']))
    baseline['realized_pnl'] = float(baseline.get('realized_pnl', 0.0))
    baseline['next_id'] = int(baseline.get('next_id', 1))
    baseline['positions'] = list(baseline.get('positions', []))
    baseline['closed_positions'] = list(baseline.get('closed_positions', []))
    baseline['events'] = list(baseline.get('events', []))
    return baseline


def save_state(state: dict, now=None) -> None:
    if _db_enabled():
        _db_save_state(state, now)
        return

    _ensure_dir()
    state['updated_at'] = _now_iso(now)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def _max_affordable_shares(cash: float, entry_price: float, commission: float) -> int:
    if entry_price <= 0:
        return 0
    unit_cost = entry_price * (1.0 + commission)
    if unit_cost <= 0:
        return 0
    return max(0, int(cash // unit_cost))


def _position_shares(entry_price: float, atr: float, cash: float, cfg: dict) -> int:
    commission = float(cfg.get('commission', 0.0015))
    capital = float(cfg.get('capital', 100_000))
    risk_pct = float(cfg.get('risk_pct', 0.005))
    sl_mult = float(cfg.get('sl_mult', cfg.get('sl_atr_mult', 1)))

    shares = 0
    if entry_price > 0 and atr > 0 and sl_mult > 0:
        risk_budget = capital * risk_pct
        stop_distance = atr * sl_mult
        if stop_distance > 0:
            shares = int(risk_budget / stop_distance)

    max_affordable = _max_affordable_shares(cash, entry_price, commission)
    if shares <= 0:
        shares = max_affordable
    return min(shares, max_affordable)


def _append_event(state: dict, event: dict) -> None:
    state['events'].append(event)
    if len(state['events']) > 200:
        state['events'] = state['events'][-200:]


def open_positions(signals: list, now, cfg: dict) -> list:
    state = load_state(cfg)
    commission = float(cfg.get('commission', 0.0015))
    sl_mult = float(cfg.get('sl_mult', cfg.get('sl_atr_mult', 1)))
    tp1_mult = float(cfg.get('tp1_mult', cfg.get('tp1_atr_mult', 2)))
    tp2_mult = float(cfg.get('tp2_mult', cfg.get('tp2_atr_mult', 4)))
    opened = []

    open_tickers = {p['ticker_full'] for p in state['positions'] if p.get('status') == 'OPEN'}

    for sig in signals:
        ticker_full = sig.get('ticker_full') or sig.get('ticker')
        if not ticker_full or ticker_full in open_tickers:
            continue
        if sig.get('criteria') != 'Prime':   # paper trade: Prime only
            continue

        entry_price = float(sig.get('close', 0) or 0)
        atr = float(sig.get('atr', 0) or 0)
        shares = _position_shares(entry_price, atr, state['cash'], cfg)
        if shares < 1:
            continue

        gross_cost = shares * entry_price
        total_cost = gross_cost * (1.0 + commission)
        if total_cost > state['cash']:
            continue

        state['cash'] -= total_cost
        position_id = state['next_id']
        state['next_id'] += 1

        position = dict(
            id=position_id,
            status='OPEN',
            ticker=sig.get('ticker', ticker_full.replace('.BK', '')),
            ticker_full=ticker_full,
            kind=sig.get('kind', ''),
            criteria=sig.get('criteria', ''),
            opened_at=_now_iso(now),
            entry_price=round(entry_price, 4),
            entry_level=round(float(sig.get('level', entry_price) or entry_price), 4),
            atr=round(atr, 4),
            shares=shares,
            gross_cost=round(gross_cost, 2),
            net_cost=round(total_cost, 2),
            sl=round(entry_price - atr * sl_mult, 4) if atr > 0 else None,
            tp1=round(entry_price + atr * tp1_mult, 4) if atr > 0 else None,
            tp2=round(entry_price + atr * tp2_mult, 4) if atr > 0 else None,
            rsm=float(sig.get('rsm', 0) or 0),
            stretch=float(sig.get('stretch', 0) or 0),
            rvol=float(sig.get('rvol', sig.get('cur_rvol', 0)) or 0),
        )
        state['positions'].append(position)
        open_tickers.add(ticker_full)

        event = dict(
            action='BUY',
            ticker=position['ticker'],
            ticker_full=ticker_full,
            at=position['opened_at'],
            price=round(entry_price, 4),
            shares=shares,
            cash_after=round(state['cash'], 2),
            net_value=round(total_cost, 2),
            criteria=position['criteria'],
            sl=position['sl'],
            tp1=position['tp1'],
            tp2=position['tp2'],
            kind=position.get('kind', ''),
            entry_level=position.get('entry_level', round(entry_price, 4)),
            rvol=position.get('rvol', 0),
            rsm=position.get('rsm', 0),
            stretch=position.get('stretch', 0),
        )
        _append_event(state, event)
        opened.append(event)

    if opened:
        save_state(state, now)
    return opened


def close_positions(signals: list, now, cfg: dict, reason: str = 'FALSE_BREAKOUT') -> list:
    state = load_state(cfg)
    commission = float(cfg.get('commission', 0.0015))
    closed = []
    price_map = {}
    for sig in signals:
        ticker_full = sig.get('ticker_full') or sig.get('ticker')
        if ticker_full:
            price_map[ticker_full] = float(sig.get('close', 0) or 0)

    keep_positions = []
    for pos in state['positions']:
        if pos.get('status') != 'OPEN':
            keep_positions.append(pos)
            continue

        exit_price = price_map.get(pos['ticker_full'])
        if not exit_price:
            keep_positions.append(pos)
            continue

        gross_exit = pos['shares'] * exit_price
        net_exit = gross_exit * (1.0 - commission)
        pnl = net_exit - float(pos.get('net_cost', 0))
        ret_pct = (exit_price - float(pos.get('entry_price', exit_price))) / float(pos.get('entry_price', 1)) * 100

        state['cash'] += net_exit
        state['realized_pnl'] += pnl

        closed_pos = dict(pos)
        closed_pos.update(
            status='CLOSED',
            closed_at=_now_iso(now),
            exit_price=round(exit_price, 4),
            net_exit=round(net_exit, 2),
            pnl=round(pnl, 2),
            ret_pct=round(ret_pct, 2),
            close_reason=reason,
        )
        state['closed_positions'].append(closed_pos)

        event = dict(
            action='SELL',
            ticker=pos['ticker'],
            ticker_full=pos['ticker_full'],
            at=closed_pos['closed_at'],
            price=round(exit_price, 4),
            shares=pos['shares'],
            cash_after=round(state['cash'], 2),
            pnl=round(pnl, 2),
            ret_pct=round(ret_pct, 2),
            reason=reason,
        )
        _append_event(state, event)
        closed.append(event)

    state['positions'] = keep_positions
    if closed:
        save_state(state, now)
    return closed


def get_summary(cfg: dict) -> dict:
    state = load_state(cfg)
    open_positions = [p for p in state['positions'] if p.get('status') == 'OPEN']
    recent_closed = state.get('closed_positions', [])[-5:]
    return dict(
        capital=round(float(state.get('capital', 0)), 2),
        cash=round(float(state.get('cash', 0)), 2),
        realized_pnl=round(float(state.get('realized_pnl', 0)), 2),
        open_count=len(open_positions),
        closed_count=len(state.get('closed_positions', [])),
        updated_at=state.get('updated_at'),
        positions=[
            dict(
                ticker=p.get('ticker'),
                ticker_full=p.get('ticker_full'),
                shares=p.get('shares'),
                entry_price=p.get('entry_price'),
                criteria=p.get('criteria'),
                sl=p.get('sl'),
                tp1=p.get('tp1'),
                tp2=p.get('tp2'),
            )
            for p in open_positions[:10]
        ],
        recent_closed=[
            dict(
                ticker=p.get('ticker'),
                pnl=p.get('pnl'),
                ret_pct=p.get('ret_pct'),
                reason=p.get('close_reason'),
            )
            for p in recent_closed
        ],
    )
