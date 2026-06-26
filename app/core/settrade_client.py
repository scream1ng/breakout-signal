"""
settrade_client.py — Singleton client for SETTRADE Open API
===========================================================
Authenticates once per session safely.
"""

import os
import time

_investor = None
_auth_ts = 0.0

# SETTRADE access tokens expire after a few hours. The web process lives for
# days, so a token cached once goes stale and every call 401s until restart.
# Re-login on a TTL well under the real expiry to stay ahead of it.
_TOKEN_TTL_S = int(os.environ.get('SETTRADE_TOKEN_TTL_S', '1800'))

def reset_session():
    """Drop the cached client so the next get_market_data() re-authenticates."""
    global _investor
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
    global _investor, _auth_ts
    if _investor is None or (time.time() - _auth_ts) > _TOKEN_TTL_S:
        load_dotenv()
        app_id = os.environ.get('SETTRADE_APP_ID')
        app_secret = os.environ.get('SETTRADE_APP_SECRET')
        broker_id = os.environ.get('SETTRADE_BROKER_ID')
        app_code = os.environ.get('SETTRADE_APP_CODE')
        
        missing = [name for name, val in [
            ('SETTRADE_APP_ID', app_id), ('SETTRADE_APP_SECRET', app_secret),
            ('SETTRADE_BROKER_ID', broker_id), ('SETTRADE_APP_CODE', app_code),
        ] if not val]
        if missing:
            raise ValueError(f"SETTRADE credentials missing in environment: {', '.join(missing)}")
            
        from settrade_v2 import Investor
        _investor = Investor(
            app_id=app_id,
            app_secret=app_secret,
            broker_id=broker_id,
            app_code=app_code,
            is_auto_queue=False
        )
        _auth_ts = time.time()
    return _investor.MarketData()
