"""
app/api/trades.py — POST /api/trades/close
============================================
Manual override to close a specific open position from the web UI.
Only available in paper mode for now (live mode raises 503).
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pytz

from app.config import TRADE_CFG, TRADE_MODE

router = APIRouter()

BKK = pytz.timezone('Asia/Bangkok')


class CloseRequest(BaseModel):
    ticker: str          # e.g. "PTT.BK"
    reason: str = 'MANUAL'


@router.post('/trades/close')
def close_trade(body: CloseRequest):
    if TRADE_MODE != 'paper':
        raise HTTPException(status_code=503, detail='Live trading not yet enabled.')

    import core.paper_trade as pt

    now   = datetime.now(BKK)
    state = pt.load_state(TRADE_CFG)

    target = next(
        (p for p in state['positions']
         if p.get('status') == 'OPEN' and p.get('ticker_full') == body.ticker),
        None,
    )
    if not target:
        raise HTTPException(status_code=404, detail=f'No open position for {body.ticker}')

    # Mark as closed at current known price (entry price used as fallback)
    closed = pt.close_positions(now, TRADE_CFG)
    return {'closed': closed}
