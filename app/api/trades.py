from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post('/trades/close')
def close_trade():
    raise HTTPException(status_code=410, detail='Paper trading removed.')


@router.delete('/trades/{trade_id}')
def delete_trade(trade_id: int):
    raise HTTPException(status_code=410, detail='Paper trading removed.')
