"""
server.py — Background scheduler and Web Server for Railway Deployment
========================================================================
Hosts the 'docs/' directory so you can view charts online.
Runs the EOD scan (main.py) automatically at 18:00 BKK every weekday.
"""

import schedule
import time
import os
import threading
import http.server
import socketserver
import subprocess

def run_eod_scan():
    print("Running EOD scan...", flush=True)
    try:
        subprocess.run(["python", "main.py", "--discord"], check=True)
        print("EOD scan completed.", flush=True)
    except Exception as e:
        print(f"EOD scan failed: {e}", flush=True)

# Railway system time is UTC. BKK (UTC+7) 18:00 = 11:00 UTC.
schedule.every().monday.at("11:00").do(run_eod_scan)
schedule.every().tuesday.at("11:00").do(run_eod_scan)
schedule.every().wednesday.at("11:00").do(run_eod_scan)
schedule.every().thursday.at("11:00").do(run_eod_scan)
schedule.every().friday.at("11:00").do(run_eod_scan)

def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    # 1. Start the scheduler in a background thread
    th = threading.Thread(target=scheduler_thread, daemon=True)
    th.start()
    
    # 2. Run an initial scan to guarantee data/HTML exists when the server spins up
    print("Initiating startup scan to generate initial dashboard...")
    run_eod_scan()
    
    # 3. Serve the docs/ directory on the Railway provided PORT
    PORT = int(os.environ.get("PORT", 8080))
    DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    
    # Ensure docs dir exists so HTTP server doesn't crash if main.py failed
    os.makedirs(DOCS_DIR, exist_ok=True)
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DOCS_DIR, **kwargs)

    print(f"Starting web server on port {PORT}...")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
