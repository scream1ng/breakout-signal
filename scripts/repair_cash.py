"""
scripts/repair_cash.py — Recalculate cash from open positions and restore equity.

Run after positions were deleted without cash being returned:
    .venv\Scripts\python scripts/repair_cash.py [--dry-run]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import app.core.paper_trade as pt
from app.config import TRADE_CFG

DRY_RUN = '--dry-run' in sys.argv

state = pt.load_state(TRADE_CFG)
commission = float(TRADE_CFG.get('commission', 0.0015))
capital = float(state.get('capital', 100_000))

open_positions = [p for p in state['positions'] if p.get('status') == 'OPEN']

# Cash locked in current open positions = shares_remaining * entry_price * (1+commission)
locked = sum(
    float(p.get('shares_remaining', p.get('shares', 0))) *
    float(p.get('entry_price', 0)) *
    (1.0 + commission)
    for p in open_positions
)

# Correct cash = capital minus locked capital
# realized_pnl already in state separately; partial TP proceeds already added to cash historically
# The simplest correct baseline: capital - locked
correct_cash = round(capital - locked, 2)

print(f"Capital:       ฿{capital:,.2f}")
print(f"Locked in {len(open_positions)} open pos: ฿{locked:,.2f}")
print(f"Current cash:  ฿{state['cash']:,.2f}")
print(f"Correct cash:  ฿{correct_cash:,.2f}")
print(f"Diff:          ฿{correct_cash - state['cash']:,.2f}")

if DRY_RUN:
    print("\n[dry-run] No changes written.")
else:
    confirm = input(f"\nSet cash to ฿{correct_cash:,.2f}? [y/N] ").strip().lower()
    if confirm == 'y':
        state['cash'] = correct_cash
        pt.save_state(state)
        print("Done. Equity restored.")
    else:
        print("Aborted.")
