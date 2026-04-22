"""
test_settrade.py — Testing ground for SETTRADE Open API
=========================================================
Before switching the breakout scanner from yfinance to Settrade,
run this script locally to verify your API credentials and test the endpoints!

Add these to your .env file:
SETTRADE_APP_ID=your_id
SETTRADE_APP_SECRET=your_secret
SETTRADE_BROKER_ID=your_broker   # e.g., '025' or 'SANDBOX'
SETTRADE_APP_CODE=your_app_code  # usually 'ALGO'
"""

import os
from settrade_v2 import Investor

def load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
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

def run_tests():
    load_dotenv()
    
    app_id = os.environ.get('SETTRADE_APP_ID')
    app_secret = os.environ.get('SETTRADE_APP_SECRET')
    broker_id = os.environ.get('SETTRADE_BROKER_ID')
    app_code = os.environ.get('SETTRADE_APP_CODE')
    
    if not all([app_id, app_secret, broker_id, app_code]):
        print("❌ ERROR: Missing Settrade credentials in .env file.")
        print("Please ensure SETTRADE_APP_ID, SETTRADE_APP_SECRET, SETTRADE_BROKER_ID, and SETTRADE_APP_CODE are set.")
        return
        
    print("🔑 Authenticating with SETTRADE...")
    try:
        investor = Investor(
            app_id=app_id,
            app_secret=app_secret,
            broker_id=broker_id,
            app_code=app_code,
            is_auto_queue=False
        )
        market = investor.MarketData()
        print("✅ Authentication successful!\n")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return

    test_ticker = "AOT"
    
    # --- Test 1: Historical Data (For End of Day Scan) ---
    print(f"📊 Test 1: Fetching Historical Candlesticks for {test_ticker}...")
    try:
        # Most Settrade Python SDKs use get_candlestick(symbol, interval, limit)
        candles = market.get_candlestick(symbol=test_ticker, interval="1d", limit=5)
        print("✅ Historical Data Retrieved!")
        
        # Determine the structure of the returned data safely
        if isinstance(candles, dict):
            # Often wrapped in a dictionary with a 'time', 'open', 'high', 'low', 'close', 'volume' keys
            # or a 'data' array depending on SDK version
            print(f"Data format received: Dictionary with keys: {list(candles.keys())}")
        elif isinstance(candles, list):
            print(f"Data format received: List with {len(candles)} items.")
        else:
            print(f"Data format received: {type(candles)}")
            
    except AttributeError:
        print("❌ 'get_candlestick' might not be the correct method name in this SDK version.")
    except Exception as e:
        print(f"❌ Historical data fetch failed: {e}")
        
    print("\n------------------------------------------------\n")
    
    # --- Test 2: Live Quote (For Intraday Check) ---
    print(f"⚡ Test 2: Fetching Live Quote for {test_ticker}...")
    try:
        quote = market.get_quote_symbol(test_ticker)
        print("✅ Live Quote Retrieved!")
        
        if isinstance(quote, dict):
            print(f"Data format received: Dictionary with keys: {list(quote.keys())[:10]}...")
            
            # Print the most critical fields if they exist
            last_price = quote.get('last') or quote.get('close') or quote.get('result', {}).get('last')
            vol = quote.get('totalVolume') or quote.get('volume') or quote.get('result', {}).get('totalVolume')
            if last_price:
                print(f"    -> Last Price: {last_price}")
            if vol:
                print(f"    -> Volume: {vol}")
        else:
            print(f"Data format received: {type(quote)}")
            
    except AttributeError:
        print("❌ 'get_quote_symbol' might not be the correct method name in this SDK version.")
    except Exception as e:
        print(f"❌ Live quote fetch failed: {e}")
        
    print("\n✅ Verification script complete!")
    print("If both tests produced a '✅', paste the results output so we can plumb the real engine!")

if __name__ == "__main__":
    run_tests()
