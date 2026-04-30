"""
app/api/trades.py — POST /api/trades/close, DELETE /api/trades/{trade_id}
===========================================================================
Manual override to close or hard-delete a position from the web UI.
Only available in paper mode for now (live mode raises 503).
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
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

    import app.core.paper_trade as pt

    now   = datetime.now(BKK)
    state = pt.load_state(TRADE_CFG)

    target = next(
        (p for p in state['positions']
         if p.get('status') == 'OPEN' and p.get('ticker_full') == body.ticker),
        None,
    )
    if not target:
        raise HTTPException(status_code=404, detail=f'No open position for {body.ticker}')

    closed = pt.close_positions(now, TRADE_CFG)
    return {'closed': closed}


@router.delete('/trades/{trade_id}')
def delete_trade(
    trade_id: int,
    kind: str = Query('open', pattern='^(open|closed)$'),
):
    """Hard-delete a position by id. Does NOT adjust cash or realized P&L."""
    if TRADE_MODE != 'paper':
        raise HTTPException(status_code=503, detail='Live trading not yet enabled.')

    import app.core.paper_trade as pt

    state = pt.load_state(TRADE_CFG)

    if kind == 'open':
        deleted_pos = next((p for p in state['positions'] if p.get('id') == trade_id), None)
        if deleted_pos is None:
            raise HTTPException(status_code=404, detail=f'Open position id={trade_id} not found')
        # Return locked capital (remaining shares) to cash
        commission = float(TRADE_CFG.get('commission', 0.0015))
        shares_remaining = float(deleted_pos.get('shares_remaining', deleted_pos.get('shares', 0)))
        entry_price = float(deleted_pos.get('entry_price', 0))
        state['cash'] = round(state['cash'] + shares_remaining * entry_price * (1.0 + commission), 2)
        state['positions'] = [p for p in state['positions'] if p.get('id') != trade_id]
    else:
        before = len(state['closed_positions'])
        state['closed_positions'] = [p for p in state['closed_positions'] if p.get('id') != trade_id]
        if len(state['closed_positions']) == before:
            raise HTTPException(status_code=404, detail=f'Closed position id={trade_id} not found')

    pt.save_state(state)
    return {'deleted': trade_id, 'kind': kind}
