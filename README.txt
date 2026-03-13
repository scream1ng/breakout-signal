================================================================================
  BREAKOUT SCANNER — Swing Trading Scanner for Thai SET
================================================================================

  Scans SET stocks daily for horizontal and trendline breakouts.
  Filters by regime (above SMA50), relative volume, and RS Momentum.
  Simulates trades with risk-based sizing, partial TP exits, and EMA10 trail.
  Publishes an interactive chart + backtest + portfolio to GitHub Pages.


================================================================================
  PROJECT STRUCTURE
================================================================================

  swing_trader/
  ├── main.py                     ← single entry point
  ├── config.py                   ← your settings (edit this)
  ├── requirements.txt
  ├── .env                        ← DISCORD_WEBHOOK= (never commit this)
  │
  ├── core/
  │   ├── data.py                 ← download + cache price data
  │   ├── entry.py                ← pivot detection, breakout signals
  │   ├── exit.py                 ← trade simulation (SL/TP/BE/EMA10)
  │   ├── portfolio.py            ← cash-aware portfolio simulation
  │   ├── rsm.py                  ← RS Momentum calculation
  │   └── scanner.py              ← TradingView pre-screen
  │
  ├── output/
  │   ├── chart_interactive.py    ← single-stock chart + signal data
  │   ├── chart_combined.py       ← combined HTML (chart + backtest + portfolio)
  │   ├── report.py               ← terminal output with ANSI colours
  │   └── discord.py              ← Discord webhook sender
  │
  ├── docs/
  │   └── index.html              ← auto-generated → served by GitHub Pages
  │
  ├── cache/                      ← price data (gitignored, auto-managed)
  │
  └── .github/
      └── workflows/
          └── daily_scan.yml      ← runs Mon-Fri 16:35 BKK


================================================================================
  COMMANDS
================================================================================

  python main.py
      Run scan. Prints breakout list to terminal.
      Generates docs/index.html (chart + backtest + portfolio).

  python main.py --discord
      Same as above + sends results to Discord webhook.

  python main.py --view
      Opens interactive chart in browser.
      Reuses today's chart if already generated (instant).
      Runs full scan first if not yet done today.

  python main.py --view TOP.BK
      Opens chart for a single stock (no full scan needed).

  python main.py --clear-cache
      Delete cached price data. Forces re-download on next run.


================================================================================
  OPTIONS (combine with any command)
================================================================================

  --period   12mo|2y      lookback period  (default: 12mo)
  --capital  200000       starting capital (default: 100000)
  --rsm      60           min RS Momentum  (default: 70)

  Examples:
    python main.py --rsm 60 --period 2y
    python main.py --view TOP.BK --period 2y
    python main.py --discord --capital 200000


================================================================================
  CONFIG (config.py)
================================================================================

  CFG = {
      'capital'        : 100_000,    # starting capital (THB)
      'risk_pct'       : 0.005,      # 0.5% risk per trade
      'rs_momentum_min': 70,         # RSM threshold
      'rvol_min'       : 1.5,        # min relative volume
      'min_turnover'   : 5_000_000,  # min daily turnover (THB)
      'commission'     : 0.0015,     # 0.15% per side
      'period'         : '12mo',     # data lookback
      'sl_atr_mult'    : 1,          # SL = entry - 1xATR
      'tp1_atr_mult'   : 2,          # TP1 = entry + 2xATR
      'tp2_atr_mult'   : 4,          # TP2 = entry + 4xATR
      'be_after_days'  : 3,          # move SL to breakeven after N bars
  }


================================================================================
  SIGNAL TYPES
================================================================================

  Priority order (chart dots + terminal + Discord):

  Prime  (pink)   RVOL >=1.5x + RSM >=70 + above SMA50   <- trade this
  STR    (red)    Prime criteria but stretch >4xATR        <- overextended, skip
  RVOL   (blue)   RVOL >=1.5x + SMA50, no RSM             <- reference only
  RSM    (green)  RSM >=70 + SMA50, no RVOL               <- reference only
  SMA50  (yellow) Above SMA50 only                        <- reference only

  Stretch = (bp - SMA50) / SMA50 / (ATR / bp)
  Measures how many ATR multiples price is extended above SMA50.
  <=4x = green tick (ok)  |  >4x = red cross (overextended)

  Backtest and Portfolio use Prime signals only.
  Chart shows all 5 types for reference.


================================================================================
  ENTRY & EXIT LOGIC
================================================================================

  ENTRY PRICE
    Limit order at break price + 1 SET tick
    Gap-up: if open > limit price, fill at open (still valid if stretch <=4x)
    Gap-up with stretch >4x: skip (STR filter)

    SET tick sizes:
      <2=0.01 | <5=0.02 | <10=0.05 | <25=0.10 | <100=0.25
      <200=0.50 | <400=1.00 | >=400=2.00

  POSITION SIZE
    Shares = (capital x 0.5%) / ATR
    Risks exactly 0.5% of capital per trade.

  STOP LOSS
    SL = entry - 1xATR  (triggers on close)
    After 3 bars: moves to entry price (breakeven)

  TAKE PROFIT
    TP1 = entry + 2xATR  -> sell 30%  (limit order)
    TP2 = entry + 4xATR  -> sell 30%  (limit order)
    Final 40% -> exit when close crosses below EMA10

  EXIT LABELS on chart:
    SL         = stopped out at loss
    Breakeven  = stopped at entry price
    TP1 / TP2  = partial take profit
    MA10       = trailed out via EMA10
    Unrealized = still open at last data bar

  COMMISSION
    0.15% per side, applied on every partial fill


================================================================================
  PORTFOLIO SIMULATION
================================================================================

  Replays Prime signals chronologically with a single cash balance.

  Rules:
    - Enter at bp + tick (or open if gap-up)
    - Only skip if insufficient cash
    - Multiple positions and re-entries on same ticker allowed
    - No max position cap

  Trade log order:
    OPEN positions at top (most recent first)
    Completed trades below (most recent first)
    SKIP rows shown inline greyed out when cash insufficient

  PnL calculation:
    ret_pct = realized_pnl / (entry_price x shares) x 100
    pnl_pct = realized_pnl / starting_capital x 100


================================================================================
  BACKTEST
================================================================================

  Runs all Prime trades independently with no cash restriction.
  Each trade uses full capital for risk sizing — no position limits.

  PnL per trade:
    ret_pct = return on invested capital for that trade

  PnL per stock:
    total_pnl_pct = sum(THB profit all trades) / starting_capital x 100

  Global Total PnL = sum of all stocks' total_pnl_pct

  Filter bar: tick Prime / STR / RVOL / RSM / SMA50 to compare strategies.
  All cards and leaderboard update instantly.


================================================================================
  INTERACTIVE CHART
================================================================================

  Sidebar
    Pink  B  = breakout signal today
    Yellow   = watchlist (active line, no breakout yet)
    Grey     = all other stocks in regime (above SMA50)

  Signal list (right panel)
    All historical signals for this stock
    Click -> analysis card (Entry / SL / TP1 / TP2 / Stretch / RSM / RVol)
    Return: +14.1% TP1v TP2v MA10  (or Unrealized if still open)

  Backtest Summary (bottom of right panel)
    Per-type stats for selected stock: Prime / STR / RVOL / RSM / SMA50

  BACKTEST tab
    Full leaderboard sorted by PnL%
    Filter checkboxes to include/exclude signal types
    Click any row -> jumps to that stock's chart

  PORTFOLIO tab
    Cash-aware simulation trade log with running balance
    Equity curve chart
    OPEN positions at top, completed trades below


================================================================================
  TERMINAL OUTPUT
================================================================================

  Colour coding:
    Magenta = Prime | Red = STR | Blue = RVOL | Green = RSM | Yellow = SMA50

  Columns: Ticker | T | Criteria | Level | Close | RVol | RSM | STR
  Sorted: Prime -> STR -> RVOL -> RSM -> SMA50 (alpha within each group)

  Followed by backtest leaderboard and summary stats.


================================================================================
  DISCORD OUTPUT
================================================================================

  Sends on --discord or GitHub Actions daily run.
  Header + signal table (auto-chunked if many signals) + chart URL.

  Columns: Ticker | T | Crit | Level | Close | RVol | RSM | STR
  Blank line between each criteria group.

  Setup:
    1. Discord -> channel settings -> Integrations -> Webhooks -> New Webhook
    2. Copy webhook URL
    3. Create .env file:  DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
    4. Test: python main.py --discord


================================================================================
  CACHING
================================================================================

  - First run downloads all stocks from Yahoo Finance -> cache/
  - Subsequent runs that day load from cache (instant)
  - Cache expires after 16:30 Bangkok time
  - GitHub Actions always downloads fresh (CI=true bypasses cache)
  - --clear-cache forces re-download on next run


================================================================================
  GITHUB PAGES SETUP (one time)
================================================================================

  1. Create public GitHub repository

  2. Push code:
       git init
       git add .
       git commit -m "initial commit"
       git branch -M main
       git remote add origin https://github.com/USERNAME/REPO.git
       git push -u origin main

  3. Enable GitHub Pages:
       repo -> Settings -> Pages
       Branch: main   Folder: /docs   -> Save

  4. Add Discord secret:
       repo -> Settings -> Environments -> create "env"
       -> Add secret: DISCORD_WEBHOOK = your webhook URL

  5. Public chart URL:
       https://USERNAME.github.io/REPO/


================================================================================
  GITHUB ACTIONS (automatic daily scan)
================================================================================

  File: .github/workflows/daily_scan.yml
  Schedule: Mon-Fri 16:35 Bangkok time (09:35 UTC)

  Steps:
    1. Download fresh price data
    2. Run scan -> generate docs/index.html
    3. Commit index.html back to repo
    4. Send Discord message (requires DISCORD_WEBHOOK secret)
    5. GitHub Pages serves updated chart

  Monitor runs:
    GitHub -> Actions tab -> Daily Scan
    Green tick = success | Red X = check logs


================================================================================
  PUSH AFTER CODE CHANGES
================================================================================

  git add .
  git commit -m "describe change"
  git push

  Trigger manually:
    GitHub -> Actions -> Daily Scan -> Run workflow

================================================================================