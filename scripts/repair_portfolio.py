"""
scripts/repair_portfolio.py — Fix corrupted paper trade DB state.

Facts (confirmed by user):
  - SCGP opened 28 Apr: 600 shares at 23.10
  - TP1 hit 29 Apr: sold 100 shares at 24.60 (via _floor_lot: int(600*0.30)=180 -> 100)
  - 500 shares remain (OPEN, tp1_hit=True)

DB corruption from manual edit:
  - pos['shares'] shows 500 (wrong — original was 600)
  - pos['shares_remaining'] shows 500 (correct)
  - pos['net_cost'] shows 11,666 (wrong — should be 600*23.10*1.0015 = 13,880.79)
  - state['cash'] shows 71,224.97 (wrong — missing TP1 proceeds + net_cost error)
  - state['realized_pnl'] shows -267.79 (missing SCGP TP1 profit)

Repairs applied:
  - SCGP: shares=600, net_cost=13,880.79, shares_remaining=500, tp1_hit=True,
           position realized_pnl=142.84
  - state.cash = 100,000 - TQM - SCGP - TPIPL + SCGP_TP1 + TPIPL_exit = 73,460.73
  - state.realized_pnl = TPIPL_loss + SCGP_TP1_profit = -124.95
  - Add SCGP TP1 event if missing

Usage:
    DATABASE_URL=postgresql://... python scripts/repair_portfolio.py
    python scripts/repair_portfolio.py  # uses hardcoded URL
"""
import json
import os
import sys
from datetime import datetime, timezone

DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:lMvuVxkYuXjHQnjCvDKqEIfhHnqZsGpJ@shinkansen.proxy.rlwy.net:21752/railway',
)

try:
    import psycopg2
except ImportError:
    print('ERROR: psycopg2 not installed.')
    sys.exit(1)


def load_state() -> dict:
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state_json FROM paper_trade_state WHERE state_key = 'default'"
            )
            row = cur.fetchone()
    if not row:
        print('ERROR: no paper_trade_state row found')
        sys.exit(1)
    return json.loads(row[0])


def save_state(state: dict) -> None:
    state['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    payload = json.dumps(state, ensure_ascii=False)
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE paper_trade_state SET state_json=%s, updated_at=now() WHERE state_key='default'",
                (payload,),
            )


COMMISSION = 0.0015

# SCGP
SCGP_ORIGINAL_SHARES = 600
SCGP_ENTRY           = 23.10
SCGP_TP1_PRICE       = 24.60
SCGP_TP1_SHARES      = 100   # _floor_lot(int(600 * 0.30)) = _floor_lot(180) = 100

scgp_gross_cost  = SCGP_ORIGINAL_SHARES * SCGP_ENTRY                         # 13,860.00
scgp_net_cost    = round(scgp_gross_cost * (1.0 + COMMISSION), 2)             # 13,880.79

tp1_net_proceeds = round(SCGP_TP1_SHARES * SCGP_TP1_PRICE * (1 - COMMISSION), 2)  # 2,456.31
tp1_cost_basis   = round(SCGP_TP1_SHARES * SCGP_ENTRY     * (1 + COMMISSION), 2)  # 2,313.47
tp1_pnl          = round(tp1_net_proceeds - tp1_cost_basis, 2)                     # 142.84

# Other known costs (confirmed from DB events / unchanged)
TQM_NET_COST   = 14_847.00
TPIPL_NET_COST =  8_940.76
TPIPL_NET_EXIT =  8_672.97
TPIPL_PNL      =   -267.79

correct_cash         = round(100_000.0 - TQM_NET_COST - scgp_net_cost - TPIPL_NET_COST
                             + tp1_net_proceeds + TPIPL_NET_EXIT, 2)
correct_realized_pnl = round(TPIPL_PNL + tp1_pnl, 2)

SCGP_LAST = 24.90
TQM_LAST  = 14.60
expected_equity = correct_cash + (1000 * TQM_LAST) + (500 * SCGP_LAST)

print('=== Repair plan ===')
print(f'  SCGP original shares  : {SCGP_ORIGINAL_SHARES}')
print(f'  SCGP net_cost (corrected): {scgp_net_cost}')
print(f'  SCGP TP1 net proceeds : {tp1_net_proceeds}')
print(f'  SCGP TP1 pnl          : {tp1_pnl}')
print(f'  Correct cash          : {correct_cash}')
print(f'  Correct realized_pnl  : {correct_realized_pnl}')
print(f'  Expected equity       : {expected_equity:.2f}  (should be > 100,000)')
print()

confirm = input('Apply? [y/N] ').strip().lower()
if confirm != 'y':
    print('Aborted.')
    sys.exit(0)

state = load_state()

# Fix top-level state
state['cash']         = correct_cash
state['realized_pnl'] = correct_realized_pnl

# Fix SCGP position
for pos in state.get('positions', []):
    if pos.get('ticker') == 'SCGP':
        print(f'  SCGP before: shares={pos.get("shares")}, shares_remaining={pos.get("shares_remaining")}, '
              f'net_cost={pos.get("net_cost")}, tp1_hit={pos.get("tp1_hit")}, realized_pnl={pos.get("realized_pnl")}')
        pos['shares']           = SCGP_ORIGINAL_SHARES      # 600
        pos['gross_cost']       = scgp_gross_cost            # 13,860.00
        pos['net_cost']         = scgp_net_cost              # 13,880.79
        pos['shares_remaining'] = SCGP_ORIGINAL_SHARES - SCGP_TP1_SHARES  # 500
        pos['tp1_hit']          = True
        pos['realized_pnl']     = tp1_pnl                   # 142.84
        print(f'  SCGP after : shares=600, shares_remaining=500, net_cost={scgp_net_cost}, '
              f'tp1_hit=True, realized_pnl={tp1_pnl}')

# Add TP1 event if not already recorded
events = state.setdefault('events', [])
already = any(e.get('ticker') == 'SCGP' and e.get('reason') == 'TP1' for e in events)
if not already:
    tp1_event = dict(
        action='SELL',
        ticker='SCGP',
        ticker_full='SCGP.BK',
        at='2026-04-29T09:25:00+00:00',
        price=SCGP_TP1_PRICE,
        shares=SCGP_TP1_SHARES,
        shares_remaining=500,
        cash_after=round(correct_cash - TPIPL_NET_EXIT + TPIPL_NET_COST, 2),
        pnl=tp1_pnl,
        reason='TP1',
    )
    events.insert(0, tp1_event)
    print(f'  Added SCGP TP1 event: {SCGP_TP1_SHARES}sh @ {SCGP_TP1_PRICE}, pnl={tp1_pnl}')

save_state(state)
print()
print('Done. Reload the web dashboard to verify equity.')
