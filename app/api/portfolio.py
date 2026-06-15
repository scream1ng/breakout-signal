from fastapi import APIRouter

router = APIRouter()


@router.get('/portfolio')
def get_portfolio():
    try:
        from app.core.paper_trader import load_trades, portfolio_summary
        from config import CFG
        store = load_trades()
        open_pos = store.get('open', [])
        closed = store.get('closed', [])

        enriched = []
        for p in open_pos:
            p = dict(p)
            cur = p.get('current_close', p['entry_price'])
            p['unrealized_pnl'] = round(
                (cur - p['entry_price']) * p['shares_remaining'] + p.get('realized_pnl', 0), 2
            )
            enriched.append(p)

        return {
            'summary': portfolio_summary(open_pos, closed, CFG),
            'open':    enriched,
            'closed':  list(reversed(closed)),
        }
    except Exception as e:
        return {'summary': {}, 'open': [], 'closed': [], 'error': str(e)}
