"""
app/api/portfolio.py — GET /api/portfolio
==========================================
Returns current paper-trade portfolio state in a clean JSON shape
suitable for the web dashboard Portfolio page.
"""

import os
import json
from fastapi import APIRouter

from app.config import TRADE_CFG, TRADE_MODE
from app.trade_engine.base import get_engine

router = APIRouter()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@router.get('/portfolio')
def get_portfolio():
    engine = get_engine()
    state  = engine.get_state(TRADE_CFG)

    capital = float(state.get('capital', 0))
    cash    = float(state.get('cash', 0))
    realized = float(state.get('realized_pnl', 0))

    positions = state.get('positions', [])
    open_pos  = [p for p in positions if p.get('status') == 'OPEN']
    closed    = state.get('closed_positions', [])

    open_value = sum(
        float(p.get('last_price', p.get('entry_price', 0))) * float(p.get('shares_remaining', p.get('shares', 0)))
        for p in open_pos
    )
    equity    = cash + realized + open_value
    ret_pct   = (equity - capital) / capital * 100 if capital > 0 else 0.0

    # Win/loss stats from closed positions
    wins   = [p for p in closed if float(p.get('pnl', 0)) > 0]
    losses = [p for p in closed if float(p.get('pnl', 0)) <= 0]
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0

    return {
        'mode':          TRADE_MODE,
        'capital':       capital,
        'cash':          cash,
        'equity':        equity,
        'realized_pnl':  realized,
        'return_pct':    round(ret_pct, 2),
        'open_count':    len(open_pos),
        'closed_count':  len(closed),
        'win_rate':      round(win_rate, 1),
        'open_positions': open_pos,
        'recent_closed':  closed[-20:][::-1],   # last 20, newest first
        'updated_at':    state.get('updated_at'),
    }
