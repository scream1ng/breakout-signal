# Breakout Signal — Swing Trading System for Thai SET

Automated breakout scanner for the Thai SET market.

Scans all SET stocks for horizontal and trendline breakouts, filters by RS Momentum and projected volume, publishes alerts to **Discord**, and status to the **web dashboard**. No paper trading. No LINE notifications.

> 📖 **New to the system?** See [OPERATIONS.md](OPERATIONS.md) for a complete guide to how scripts work, when they run, and how to monitor the dashboard.

---

## HOW IT WORKS — END TO END

```
TradingView universe
      │
      ▼
app/core/scanner.py     ← fetch ~600 SET stocks via TradingView API
      │
      ▼
app/core/data.py        ← download OHLCV + cache to disk (SETTRADE API → yfinance fallback)
      │
      ▼
app/core/entry.py       ← detect horizontal + trendline breakout pivots
app/core/rsm.py         ← calculate RS Momentum vs ^SET.BK benchmark
      │
      ▼
main.py (EOD)           ← rank, filter, classify (Prime/RVOL/RSM/STR/SMA50)
intraday.py (live)      ← check watchlist every 15 min against live prices
      │
       ├─► output/chart_interactive.py ← build per-stock chart dict (candles/EMA/SMA/signals/trades)
       │                                  → saved to ChartData table (one small row per signal/watchlist ticker)
       └─► output/notifications.py   ← Discord alerts (intraday / fakeout / EOD)
      │
      ▼
app/scheduler/runner.py ← APScheduler calls main.py + intraday.py on schedule
      │                    writes JobRun row to DB on every execution
      ▼
main_app.py             ← FastAPI serves web dashboard + REST API
      │                    GET /api/chart/{ticker} serves one stock's chart JSON on demand
      ▼
Browser: http://localhost:8080  (single-page React app — slim icon rail, 5 tabs + FAQ drawer)
  ├── Chart      → chart panel (native lightweight-charts) + watchlist / alerts / fakeouts / EOD
  ├── Screener   → Relative Rotation Graph over the above-SMA50 tradable universe (sector roll-up → drill)
  ├── Portfolio  → equity KPIs, open positions, closed trades
  ├── Backtest   → per-symbol breakout stats
  └── Jobs       → scheduler status, manual runs, live console (merged old Tools)
```

---

## PROJECT STRUCTURE

```text
breakout-signal/
├── main.py                 ← EOD scan CLI (unchanged — called by scheduler + directly)
├── intraday.py             ← Intraday scan CLI (unchanged)
├── backtest_optimize.py    ← Parameter optimizer (standalone tool)
├── main_app.py             ← FastAPI entry point (replaces server.py)
├── config.py               ← Global trade settings (edit this)
├── requirements.txt
├── Procfile                ← Railway: uvicorn main_app:app
├── .env                    ← Secrets — NEVER commit
│
├── app/
│   ├── config.py           ← Centralised env loader (reads .env once)
│   │
│   ├── core/               ← All trading logic
│   │   ├── data.py         ← Price download + daily cache
│   │   ├── settrade_client.py ← SETTRADE OpenAPI session
│   │   ├── entry.py        ← Pivot detection (Hz + trendline)
│   │   ├── exit.py         ← Backtest simulator (SL/TP/BE/EMA10)
│   │   ├── paper_trade.py  ← Live paper trade ledger (Postgres or JSON)
│   │   ├── portfolio.py    ← Cash-aware backtest portfolio
│   │   ├── rsm.py          ← RS Momentum vs benchmark
│   │   ├── rrg.py          ← Screener Relative Rotation Graph universe (RSM-100 × RSM-21, median-centered)
│   │   └── scanner.py      ← TradingView pre-screen
│   │
│   ├── trade_engine/       ← Abstraction layer (swap paper → live via env var)
│   │   ├── base.py         ← Abstract TradeEngine interface
│   │   ├── paper.py        ← PaperTradeEngine (wraps core/paper_trade.py)
│   │   └── live.py         ← LiveTradeEngine stub (SETTRADE orders — Phase 5)
│   │
│   ├── notifications/
│   │   ├── line.py         ← New LINE notifier module (not yet the scheduled path)
│   │   └── discord.py      ← Job failure + system alert helpers
│   │
│   ├── scheduler/
│   │   ├── jobs.py         ← Job definitions (eod_scan, intraday_scan, review)
│   │   └── runner.py       ← APScheduler + JobRun DB tracking
│   │
│   ├── api/
│   │   ├── system.py       ← GET /api/system
│   │   ├── portfolio.py    ← GET /api/portfolio
│   │   ├── signals.py      ← GET /api/signals
│   │   ├── scan.py         ← GET /api/scan/latest, /api/backtest, /api/watchlist/detail, /api/chart/{ticker}, /api/screener
│   │   └── trades.py       ← POST /api/trades/close
│   │
│   ├── storage/
│   │   ├── models.py       ← SQLAlchemy models (JobRun, ScanSnapshot, ChartData, DailyState, NotificationSend)
│   │   ├── state.py        ← DB key/value + per-ticker chart store (save_chart/load_chart/prune_charts)
│   │   └── db.py           ← DB session (Postgres → SQLite fallback)
│   │
│   └── logs/               ← Structured job logs (future use)
│
├── frontend/               ← Web dashboard SPA (React 18 via CDN + Babel, no build step)
│   ├── index.html          ← Terminal CSS + font/script wiring
│   └── static/
│       ├── bs-data.jsx     ← shared helpers (formatters, tickerText/Full, CC, CRIT_COLOR)
│       ├── bs-app.jsx      ← app shell: topbar, slim nav rail, 4 tabs, all API/state
│       ├── bs-views.jsx    ← views: chart workspace, portfolio, backtest, jobs, FAQ drawer
│       ├── bt-chart.jsx    ← React chart panel (fetches /api/chart/{ticker})
│       ├── bt-screener.jsx ← Screener RRG view (sector roll-up → drill → click symbol opens its chart)
│       └── lwc-render.js   ← shared lightweight-charts renderer (also inlined by --view)
│
├── output/                 ← Chart data builder + CLI --view
│   ├── chart_interactive.py ← get_chart_data() → per-stock dict (candles/EMA/SMA/signals/trades)
│   ├── chart_combined.py    ← generate_view_html() — slim single-ticker standalone for `main.py --view`
│   ├── report.py
│   └── notifications.py     ← Discord (used by CLI scripts)
│
├── tests/
│   ├── test_notifications.py
│   └── test_settrade.py
│
├── docs/                   ← Auto-generated chart HTML (served at /docs/)
└── data/
    ├── watchlist.json
    ├── alert_state.json
    ├── paper_portfolio.json   ← Paper trade state (fallback, no Postgres)
    └── notification_outbox.jsonl
```

---

## SIGNAL CRITERIA

| Label | Condition | Discord alert | Paper trade |
|---|---|---|---|
| **Prime** | proj_rvol ≥ 2× **and** RSM ≥ 80 **and** stretch ≤ 4 | ✓ Intraday/EOD alert | ✓ Opens position |
| **RVOL** | proj_rvol ≥ 2×, RSM below threshold | ✓ Intraday/EOD alert | — |
| **RSM** | RSM ≥ 80, proj_rvol below threshold | ✓ EOD alert | — |
| **SMA50** | Above SMA50 only | ✓ EOD alert | — |
| **STR** | stretch > 4 (overextended) | ✓ Intraday/EOD alert | — |

> Intraday uses **projected RVol** — full-day volume projected from time elapsed in SET session (10:00–12:30 + 14:00–16:30 = 300 min total).
> Intraday Discord table shows **Proj RVol** (with current RVOL only as fallback).
> EOD is a fresh full-market close scan. An intraday fire from yesterday's watchlist should appear in today's EOD results only if it still qualifies on the final daily close. EOD shows all close-qualified signals, not every intraday touch.

---

## PAPER TRADE EXIT LOGIC

Checked every intraday scan. Size formula: `capital × risk_pct / (ATR × sl_mult)`

| Exit | Trigger | Action |
|---|---|---|
| **TP1** | close ≥ entry + 2×ATR | Sell 30% |
| **Breakeven** | After `be_days` (3) bars | Move SL → entry |
| **TP2** | close ≥ entry + 4×ATR | Sell ~30% of remaining |
| **EMA10 trail** | close < EMA10 | Exit remaining |
| **SL** | close ≤ stop | Exit all |
| **False breakout** | 16:25 review: close < pivot | Exit all |

---

## Notification Routing

Current scheduled flow:

- Discord sends alerting output: intraday breakouts, fakeout review, EOD summary.
- LINE sends paper-trade output: trade opened, TP/SL exits, portfolio snapshot, trade history.

| Notification | Trigger | Type |
|---|---|---|
| **Intraday breakout** | Live break during session | Discord table alert |
| **Fakeout warning** | 16:25 review | Discord fakeout alert |
| **EOD summary** | 16:45 scan | Discord summary table |
| **Trade opened** | Prime signal → paper buy | LINE bubble: entry, shares, RVol/RSM/STR |
| **TP1 / TP2** | Partial exit hit | LINE bubble: tranche P&L, shares left, next target |
| **Trade closed** | SL / trail / false breakout | LINE bubble: final P&L |
| **Portfolio snapshot** | EOD | LINE portfolio summary |
| **Trade history** | EOD | LINE trade history table |

Paper-trade entry records use **Proj RVol** first, then fallback to current RVOL only if projected value is unavailable.

---

## RUNNING LOCALLY

**First time setup:**
```bash
uv venv
uv pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

**Start the web app + scheduler:**
```bash
.venv\Scripts\uvicorn main_app:app --reload --port 8080
# Open http://localhost:8080
```

**Run scans manually (CLI — do not need the web app running):**
```bash
# EOD scan — generate chart + watchlist + Discord alert + LINE paper-trade summary
.venv\Scripts\python main.py

# Intraday scan — check watchlist against live prices + Discord alerts + LINE trade updates
.venv\Scripts\python intraday.py

# Fakeout review
.venv\Scripts\python intraday.py --review

# View interactive chart in browser
.venv\Scripts\python main.py --view

# Backtest optimizer
.venv\Scripts\python backtest_optimize.py --top 10 --workers 4

# Clear price cache
.venv\Scripts\python main.py --clear-cache
```

**Override config temporarily:**
```bash
.venv\Scripts\python main.py --period 2y --capital 200000 --rsm 60
```

**Automated API/workflow smoke tests:**
```bash
.venv\Scripts\python -m pytest -q tests/test_api_smoke.py
```

**Manual notification/API connectivity checks:**
```bash
.venv\Scripts\python -m tests.test_notifications
.venv\Scripts\python -m tests.test_settrade
```

---

## WEB DASHBOARD

Open `http://localhost:8080` after starting the app. Single-page React app — slim 66px icon rail, five tabs, FAQ as a slide-out drawer.

| Tab | Content |
|---|---|
| **Chart** | Chart panel (native lightweight-charts: candles, EMA10/EMA20/SMA50, buy/sell markers, breakout level) + tabbed right panel: Watchlist (grouped by MA10/MA20/MA50) / Alerts / Fakeouts / EOD. Click any row to load its chart. |
| **Screener** | Relative Rotation Graph of the **above-SMA50 tradable universe** (every liquid SET stock above SMA50, not just watchlist/breakout names). Axes = RSM-100 (established) × RSM-21 (recent), median-centered. Default = sector roll-up; click a sector (dot or row) to drill into its members; click a symbol to open its chart. Built by the EOD scan, served from `/api/screener`. |
| **Portfolio** | Equity / Open P&L / Realized / Exposure KPIs, open positions, closed trades |
| **Backtest** | Per-symbol breakout stats, criteria filter (Prime/STR/RVOL/RSM/SMA50) |
| **Jobs** | Scheduler job cards (Run now), recent runs, live console, Discord notify test (merged old Tools) |

Auto-refreshes every 60 seconds. All data comes from the REST API:

| Endpoint | Returns |
|---|---|
| `GET /api/system` | Scheduler running, next run times, job run history |
| `GET /api/portfolio` | Positions, equity, win rate, recent closed trades |
| `GET /api/signals` | Watchlist + today's triggered breaks |
| `GET /api/scan/latest` | Latest EOD scan summary + signals |
| `GET /api/backtest` | Per-ticker backtest rows + overall stats |
| `GET /api/watchlist/detail` | Watchlist grouped by MA position + TradingView copy string |
| `GET /api/chart/{ticker}` | One stock's chart JSON — stored ChartData row, else live candles+MA rebuild |
| `GET /api/screener` | RRG universe (sectors + member stocks, RSM-100/RSM-21, median + axis gains) from the latest EOD scan |
| `POST /api/trades/close` | Manually close a position |

Charts render natively in the SPA from `/api/chart/{ticker}`. The EOD scan writes one small `ChartData` row per signal/watchlist ticker (survives Railway redeploys); any other ticker is rebuilt on demand from cached OHLCV. The legacy `/chart` URL now redirects into the SPA.

---

## RAILWAY DEPLOYMENT

1. Push branch to GitHub → open PR → merge to `main`
2. Railway → **New** → **Deploy from GitHub repo** (or auto-deploys on push to `main`)
3. Set **Variables** in Railway dashboard:

```ini
# Required
LINE_CHANNEL_ACCESS_TOKEN=your_token
LINE_TO=your_user_or_group_id         # comma-separated for multiple

# Recommended
DATABASE_URL=postgresql://...         # Postgres add-on in Railway
APP_BASE_URL=https://your-app.up.railway.app
TRADE_MODE=paper                      # paper | live

# Optional ops alerts
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

# SETTRADE OpenAPI (live price data + future live trading)
SETTRADE_APP_ID=...
SETTRADE_APP_SECRET=...
SETTRADE_BROKER_ID=...
SETTRADE_APP_CODE=...
```

4. Railway → **Settings → Networking → Generate Domain**

**Production preflight (must pass before replacing existing service):**
```bash
# 1) Syntax safety
py -m compileall app main_app.py output

# 2) Automated API/workflow smoke checks
py -m pytest -q tests/test_api_smoke.py

# 3) Optional manual notification/settrade checks
py -m tests.test_notifications
py -m tests.test_settrade
```

**Automated schedule (APScheduler, runs inside the web process):**

| Time (BKK) | UTC | Job |
|---|---|---|
| 10:30–12:30, 14:00–16:15 every 15 min | 03:30–05:30, 07:00–09:15 | `intraday_scan` |
| 16:25 | 09:25 | `review_scan` (fakeout check) |
| 16:45 | 09:45 | `eod_scan` |

Every job writes a `JobRun` row to the database — visible in real-time on the Dashboard tab.

---

## SWITCHING PAPER → LIVE TRADING

When ready to go live, only one file needs to change:

1. Set `TRADE_MODE=live` in Railway variables
2. Implement `app/trade_engine/live.py` using the SETTRADE order API
3. All other code (scanner, entry, notifications, dashboard) is untouched

---

## .ENV FILE

```ini
# Web app public URL (used in notification links)
APP_BASE_URL="https://your-service.up.railway.app"

# Postgres (Railway — required for scheduler locking/history/audit)
DATABASE_URL="postgresql://..."

# SETTRADE OpenAPI
SETTRADE_APP_ID="your_app_id"
SETTRADE_APP_SECRET="your_app_secret"
SETTRADE_BROKER_ID="your_broker_id"
SETTRADE_APP_CODE="your_app_code"

# Discord alerts
DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."

# Optional — protect manual ops endpoints in production
OPS_API_TOKEN="long-random-token"

# Legacy / unused in current runtime
# LINE_CHANNEL_ACCESS_TOKEN="your_token"
# LINE_TO="your_user_or_group_id"
# LINE_MODE="broadcast"
```
