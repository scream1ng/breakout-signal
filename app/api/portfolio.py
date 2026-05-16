from fastapi import APIRouter

router = APIRouter()


@router.get('/portfolio')
def get_portfolio():
    return {'message': 'Portfolio removed — paper trading disabled.'}
