================================================================================
  PB SCANNER — Pivot Breakout Scanner for Thai SET
================================================================================

  Scans SET stocks daily for horizontal and trendline breakouts.
  Filters by regime (above SMA50), relative volume, and RS Momentum.
  Publishes an interactive chart to GitHub Pages automatically.


================================================================================
  PROJECT STRUCTURE
================================================================================

  breakout-signal/
  ├── main.py                     ← single entry point
  ├── config.py                   ← your settings (edit this)
  ├── requirements.txt
  ├── .env                        ← DISCORD_WEBHOOK= (never commit this)
  │
  ├── core/
  │   ├── data.py                 ← download + cache price data
  │   ├── entry.py                ← pivot detection, breakout signals
  │   ├── exit.py                 ← trade simulation (SL/TP/BE/EMA10)
  │   ├── rsm.py                  ← RS Momentum calculation
  │   └── scanner.py              ← TradingView pre-screen
  │
  ├── output/
  │   ├── chart_interactive.py    ← single-stock chart data
  │   ├── chart_combined.py       ← combined HTML (all stocks)
  │   └── discord.py              ← Discord webhook sender
  │
  ├── docs/
  │   └── index.html              ← auto-generated → served by GitHub Pages
  │
  ├── cache/                      ← price data (gitignored, auto-managed)
  │
  └── .github/
      └── workflows/
          └── daily_scan.yml      ← runs Mon–Fri 16:35 BKK


================================================================================
  COMMANDS
================================================================================

  python main.py
      Run scan. Prints breakout list + watchlist to terminal.
      Also updates docs/index.html (interactive chart).

  python main.py --discord
      Same as above + sends results to Discord.

  python main.py --view
      Opens interactive chart in browser.
      Reuses today's chart if already generated (instant).
      Runs full scan first if not yet done today.

  python main.py --view TOP.BK
      Opens chart for a single stock.

  python main.py --clear-cache
      Delete cached price data. Forces re-download on next run.


================================================================================
  OPTIONS (combine with any command)
================================================================================

  --period  12mo|2y       lookback period  (default: 12mo)
  --capital 200000        starting capital (default: 100000)
  --rsm     60            min RS Momentum  (default: 70)

  Examples:
    python main.py --rsm 60 --period 2y
    python main.py --view TOP.BK --period 2y


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
      'sl_atr_mult'    : 1,          # SL = entry - 1×ATR
      'tp1_atr_mult'   : 2,          # TP1 = entry + 2×ATR
      'tp2_atr_mult'   : 4,          # TP2 = entry + 4×ATR
      'be_after_days'  : 3,          # breakeven after N bars
  }


================================================================================
  ENTRY & EXIT LOGIC
================================================================================

  ENTRY FILTERS (3 tiers shown on chart)
    Full         : above SMA50 + RVol ≥ 1.5x + RSM ≥ 70
    No RSM       : above SMA50 + RVol ≥ 1.5x
    Regime only  : above SMA50 only

  ENTRY PRICE
    Break price + 1 SET tick (realistic limit order above level)
    SET tick sizes: <฿2 = 0.01 | <฿5 = 0.02 | <฿10 = 0.05 |
                    <฿25 = 0.10 | <฿100 = 0.25 | <฿200 = 0.50 |
                    <฿400 = 1.00 | ≥฿400 = 2.00

  STOP LOSS
    SL = entry − 1×ATR
    Triggers when close ≤ SL (end-of-day check)
    After 3 bars → moves to entry price (breakeven)

  TAKE PROFIT
    TP1 = entry + 2×ATR  → sell 30%  (limit order)
    TP2 = entry + 4×ATR  → sell 30%  (limit order)
    Final 40% → exits when close < EMA10

  ALL SL/BE/MA10 EXITS → at close price
  TP1/TP2 EXITS        → at target price (limit order)

  POSITION SIZE
    Shares = (capital × 0.5%) ÷ ATR
  COMMISSION
    0.15% per side, applied on every partial fill


================================================================================
  SIGNALS COLUMN GUIDE
================================================================================

  Ticker   : stock symbol (without .BK)
  T        : Hz = horizontal breakout | TL = trendline breakout
  Criteria : Full | No RSM | Regime
  Level    : pivot level being broken (entry reference)
  Close    : last closing price
  RVol     : today's volume ÷ 20-day avg (green if ≥ 1.5x)
  RSM      : RS Momentum 0–100 (higher = stronger vs SET index)
  ATR%     : ATR as % of close (wider = more volatile)


================================================================================
  INTERACTIVE CHART
================================================================================

  Sidebar
    Pink  ▲  =  breakout signal today
    Yellow   =  watchlist (active line, no breakout yet)
    Grey     =  all other stocks above SMA50
    RVol shown in green if ≥ 1.5x

  Right panel — SIGNALS tab
    Lists all historical signals for selected stock
    Click signal → analysis card (entry / SL / TP1 / TP2 / RSM / RVol)
    Return shown green (profit) or red (loss)

  Right panel — BACKTEST SUMMARY
    Per-filter stats: Full | No RSM | Regime only
    WR% and avg return for each filter tier

  BACKTEST tab (top right)
    Full leaderboard: all stocks sorted by PnL%
    Summary cards: trades, win rate, avg win, avg loss
    Click any row → jumps to that stock's chart


================================================================================
  CACHING
================================================================================

  - First run each day downloads all stocks from Yahoo Finance → cache/
  - Subsequent runs that day load from cache instantly
  - Cache expires after 16:30 Bangkok time (SET close)
  - GitHub Actions always downloads fresh (CI=true bypasses cache)
  - --clear-cache forces re-download on next run


================================================================================
  DISCORD SETUP
================================================================================

  1. Discord → channel settings → Integrations → Webhooks → New Webhook
  2. Copy Webhook URL
  3. Create .env file in project root:

       DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

  4. Test:
       python main.py --discord

  Message format (single message):
    PB Scanner  |  2026-03-11
    112 above SMA50  ·  80 watchlist  ·  3 breakouts
    ┌─────────────────────────────────────────────────┐
    │ Ticker  T  Criteria  Level    Close   RVol  RSM  ATR
    │ TOP     Hz  Full     277.64   280.00  2.3x   74  1.8%
    └─────────────────────────────────────────────────┘
    https://scream1ng.github.io/breakout-signal/


================================================================================
  GITHUB SETUP (one time)
================================================================================

  1. Create a public GitHub repository

  2. In project folder:
       git init
       git add .
       git commit -m "initial commit"
       git branch -M main
       git remote add origin https://github.com/USERNAME/REPO.git
       git push -u origin main

  3. Enable GitHub Pages:
       repo → Settings → Pages
       Branch: main   Folder: /docs   → Save

  4. Add Discord secret (optional):
       repo → Settings → Environments → create environment "env"
       → Add secret: DISCORD_WEBHOOK = your webhook URL

  5. Public chart URL:
       https://USERNAME.github.io/REPO/


================================================================================
  GITHUB ACTIONS (automatic daily scan)
================================================================================

  File: .github/workflows/daily_scan.yml
  Schedule: Mon–Fri 16:35 Bangkok time (09:35 UTC)

  What it does:
    1. Downloads fresh price data
    2. Runs scan → generates docs/index.html
    3. Commits index.html back to repo
    4. Sends Discord message (requires DISCORD_WEBHOOK secret)
    5. GitHub Pages serves updated chart publicly

  Monitor:
    GitHub → Actions tab → Daily Scan
    Green tick = success | Red X = check logs


================================================================================
  PUSH AFTER CODE CHANGES
================================================================================

  git add .
  git commit -m "describe change"
  git push

  Trigger manually without waiting for 16:35:
    GitHub → Actions → Daily Scan → Run workflow

================================================================================