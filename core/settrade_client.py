"""
settrade_client.py — Singleton client for SETTRADE Open API
===========================================================
Authenticates once per session safely.
"""

import os

_investor = None

def load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip(); val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

def get_market_data():
    """Returns the authenticated MarketData object, or raises an Exception if failed."""
    global _investor
    if _investor is None:
        load_dotenv()
        app_id = os.environ.get('SETTRADE_APP_ID')
        app_secret = os.environ.get('SETTRADE_APP_SECRET')
        broker_id = os.environ.get('SETTRADE_BROKER_ID')
        app_code = os.environ.get('SETTRADE_APP_CODE')
        
        if not all([app_id, app_secret, broker_id, app_code]):
            raise ValueError("SETTRADE credentials missing in environment.")
            
        from settrade_v2 import Investor
        _investor = Investor(
            app_id=app_id,
            app_secret=app_secret,
            broker_id=broker_id,
            app_code=app_code,
            is_auto_queue=False
        )
    return _investor.MarketData()
