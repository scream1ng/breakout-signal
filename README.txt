================================================================================
  PB SCANNER — Pivot Breakout Scanner for Thai SET
  README / Setup & Usage Guide
================================================================================

FOLDER STRUCTURE
────────────────
swing_trader/
├── main.py                         ← single entry point for ALL commands
├── config.py                       ← your personal settings (edit this)
├── requirements.txt                ← Python dependencies
│
├── core/                           ← signal logic (don't need to edit often)
│   ├── data.py                     ← download & cache price data
│   ├── entry.py                    ← pivot detection, breakout signals
│   ├── exit.py                     ← trade simulation (SL, TP, BE, EMA10)
│   ├── rsm.py                      ← RS Momentum calculation
│   └── scanner.py                  ← TradingView pre-screen
│
├── output/                         ← everything you see (charts + terminal)
│   ├── report.py                   ← terminal output (screener, backtest)
│   ├── chart.py                    ← PNG chart (used with --save only)
│   ├── chart_interactive.py        ← single-stock interactive HTML
│   └── chart_combined.py           ← combined HTML (all stocks, sidebar)
│
├── web/
│   └── index.html                  ← auto-generated after each scan
│                                      committed to git → served by GitHub Pages
│
├── cache/                          ← price data parquet files (auto-managed)
│                                      gitignored — re-downloads automatically
│
├── scripts/
│   └── cron_push.sh                ← optional local cron (backup)
│
└── .github/
    └── workflows/
        └── daily_scan.yml          ← GitHub Actions: runs scan daily at 16:35 BKK
                                       auto-commits web/index.html to repo


================================================================================
  FIRST TIME SETUP (LOCAL)
================================================================================

1. Install Python 3.11+  →  https://python.org

2. Copy the project folder to your computer

3. Open terminal in the project folder, install dependencies:
      pip install -r requirements.txt

4. Edit config.py to set your capital, RSM threshold, etc.

5. Run your first scan:
      python main.py

   Data downloads and caches automatically on first run.


================================================================================
  DAILY COMMANDS
================================================================================

  python main.py
      Screener: shows today's breakout list + watchlist
      Saves web/index.html (combined interactive chart)

  python main.py --view
      Opens web/index.html in browser
      Reuses today's chart if already generated (instant)
      Runs full scan first if not yet generated today

  python main.py --view TOP.BK
      Opens interactive chart for TOP.BK only in browser

  python main.py --backtest
      Full backtest: leaderboard + summary for all stocks

  python main.py --backtest TOP.BK
      Backtest single stock: every trade listed + summary

  python main.py --save
      Add to any command to save individual PNG + HTML charts
      Example: python main.py --save
      Example: python main.py --backtest TOP.BK --save

  python main.py --clear-cache
      Delete all cached price data (forces fresh download next run)


================================================================================
  OPTIONS (combine with any command)
================================================================================

  --period  12mo|2y       lookback period  (default: 12mo)
  --capital 200000        starting capital (default: 100000)
  --rsm     60            min RS Momentum  (default: 70)
  --save                  save individual charts to output/charts/

  Examples:
    python main.py --rsm 60
    python main.py --backtest --period 2y --capital 200000
    python main.py --view TOP.BK --period 2y


================================================================================
  HOW CACHING WORKS
================================================================================

  - First run each day downloads all stocks from Yahoo Finance → cache/
  - All runs after that load from cache instantly
  - Cache expires after 16:30 Bangkok time (SET market close)
  - Next run after 16:30 re-downloads to get end-of-day prices
  - --clear-cache forces immediate re-download on next run


================================================================================
  GITHUB SETUP (one time)
================================================================================

  1. Create a GitHub account → https://github.com

  2. Create a new PUBLIC repository called "swing-trader"

  3. In your project folder terminal:

       git init
       git add .
       git commit -m "initial commit"
       git branch -M main
       git remote add origin https://github.com/YOURUSERNAME/swing-trader.git
       git push -u origin main

     When asked for password, use a Personal Access Token:
       GitHub → Settings → Developer settings → Personal access tokens
       → Tokens (classic) → Generate new token → check "repo" → copy token

  4. Enable GitHub Pages:
       GitHub → repo → Settings → Pages
       Source: Deploy from branch
       Branch: main   Folder: /web   → Save

  5. Your public site:
       https://YOURUSERNAME.github.io/swing-trader/

     Share this URL with your friend — updates automatically every day.


================================================================================
  UPDATING GITHUB AFTER CODE CHANGES (every time you edit files)
================================================================================

  git add .
  git commit -m "describe what you changed"
  git push

  GitHub Actions will use your new code on the next daily run.

  To test immediately without waiting for 16:35:
    GitHub → repo → Actions → Daily Scan → Run workflow button


================================================================================
  GITHUB ACTIONS (automatic daily scan)
================================================================================

  File: .github/workflows/daily_scan.yml

  - Runs Mon–Fri at 16:35 Bangkok time (09:35 UTC)
  - Downloads fresh data, runs python main.py
  - Commits updated web/index.html back to repo
  - GitHub Pages serves it publicly

  Check results:
    GitHub → Actions tab → green tick = success, red X = error


================================================================================
  SCREENER OUTPUT — COLUMN GUIDE
================================================================================

  Type   : Horiz Break = horizontal pivot  |  TL Break = descending trendline
  Level  : the price level being broken (your entry reference)
  Close  : last closing price
  Gap%   : distance from close to level
  RVol   : volume vs 20-day average  (1.5x = 50% above average)
  RSM    : RS Momentum 0–100  (higher = stronger stock vs SET index)
  ATR%   : ATR as % of close  (wider = more volatile, wider stop)


================================================================================
  BACKTEST — HOW IT WORKS
================================================================================

  Entry   : max(level price, open)  — gap-up fills at open, not level
  SL      : entry − 1×ATR
  TP1     : entry + 2×ATR  → close 30% of position
  TP2     : entry + 4×ATR  → close 30% of position
  Final   : remaining 40% exits when close < EMA10
  BE      : after 3 bars, SL moves to entry price (breakeven)
  Size    : capital × 0.5% / ATR  (fixed risk per trade)
  Cost    : 0.15% commission per side

  Avg Gain% and Avg Loss% = return from entry price (not % of capital)
  e.g. buy ฿50, exit ฿54 = +8.0%


================================================================================
  OLD FILES TO DELETE (once new structure confirmed working)
================================================================================

  Delete these from project root — replaced by core/ and output/ folders:

    entry.py            → now core/entry.py
    exit.py             → now core/exit.py
    rsm.py              → now core/rsm.py
    scanner.py          → now core/scanner.py
    chart.py            → now output/chart.py
    chart_interactive.py → now output/chart_interactive.py
    chart_combined.py   → now output/chart_combined.py
    viewer.py           → replaced by --view command
    scan.py             → replaced by main.py

================================================================================
