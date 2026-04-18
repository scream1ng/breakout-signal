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

def run_intraday_scan(review=False):
    lbl = "review" if review else "scan"
    print(f"Running intraday {lbl}...", flush=True)
    try:
        cmd = ["python", "intraday.py", "--discord"]
        if review: cmd.append("--review")
        subprocess.run(cmd, check=False)
        print(f"Intraday {lbl} completed.", flush=True)
    except Exception as e:
        print(f"Intraday {lbl} failed: {e}", flush=True)

def schedule_intraday(time_bkk, is_review=False):
    h, m = map(int, time_bkk.split(':'))
    h_utc = (h - 7) % 24
    utc_str = f"{h_utc:02d}:{m:02d}"
    
    for day in [schedule.every().monday, schedule.every().tuesday, 
                schedule.every().wednesday, schedule.every().thursday, 
                schedule.every().friday]:
        day.at(utc_str).do(run_intraday_scan, review=is_review)

# 15-minute Normal Intraday Scans
for t in ["10:30", "10:45", "11:00", "11:15", "11:30", "11:45", "12:00", "12:15", "12:30",
          "14:30", "14:45", "15:00", "15:15", "15:30", "15:45", "16:00"]:
    schedule_intraday(t)

# 16:15 Fakeout Review Scan
schedule_intraday("16:15", is_review=True)

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
