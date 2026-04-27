# Breakout Signal — Swing Trading System for Thai SET

Automated breakout scanner and paper trading system for the Thai SET market.

Scans all SET stocks for horizontal and trendline breakouts, filters by RS Momentum and projected volume, simulates paper trades with risk-based sizing and partial TP exits, publishes alerts to **Discord**, paper-trade updates to **LINE**, and status to the **web dashboard**.

Currently running in **paper trade mode** (simulated fills). Switch to live trading via `TRADE_MODE=live` once SETTRADE order API is wired up.

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
       ├─► output/chart_combined.py  ← generate docs/index.html (interactive chart)
       ├─► app/core/paper_trade.py   ← open/close/check positions (paper ledger)
       └─► output/notifications.py   ← current scheduled notification path
             ├─ Discord → intraday / fakeout / EOD alerts
             └─ LINE    → paper-trade entry / exit / summary
      │
      ▼
app/scheduler/runner.py ← APScheduler calls main.py + intraday.py on schedule
      │                    writes JobRun row to DB on every execution
      ▼
main_app.py             ← FastAPI serves web dashboard + REST API
      │
      ▼
Browser: http://localhost:8080
  ├── /              → Dashboard tab  (scheduler status, job history)
  ├── /portfolio     → Portfolio tab  (positions, P&L, trade history)
  ├── /signals       → Signals tab    (today's breaks, watchlist)
  └── /docs/         → Chart view     (generated HTML chart, unchanged)
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
│   │   └── trades.py       ← POST /api/trades/close
│   │
│   ├── storage/
│   │   ├── models.py       ← SQLAlchemy models (JobRun)
│   │   └── db.py           ← DB session (Postgres → SQLite fallback)
│   │
│   └── logs/               ← Structured job logs (future use)
│
├── frontend/               ← Web dashboard SPA
│   ├── index.html          ← Alpine.js + Tailwind — 3 tabs
│   └── static/
│       ├── app.js          ← All fetch + UI logic
│       └── style.css       ← Custom overrides
│
├── output/                 ← Chart generation (unchanged)
│   ├── chart_interactive.py
│   ├── chart_combined.py
│   ├── report.py
│   └── notifications.py    ← Legacy — Discord + LINE (still used by CLI scripts)
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
| **False breakout** | 16:15 review: close < pivot | Exit all |

---

## Notification Routing

Current scheduled flow:

- Discord sends alerting output: intraday breakouts, fakeout review, EOD summary.
- LINE sends paper-trade output: trade opened, TP/SL exits, portfolio snapshot, trade history.

| Notification | Trigger | Type |
|---|---|---|
| **Intraday breakout** | Live break during session | Discord table alert |
| **Fakeout warning** | 16:15 review | Discord fakeout alert |
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

Open `http://localhost:8080` after starting the app.

| Tab | URL | Content |
|---|---|---|
| **Dashboard** | `/` | Scheduler status, job cards (last run / next run / duration / error), run history table |
| **Portfolio** | `/portfolio` | Equity summary, open positions, closed trade history |
| **Signals** | `/signals` | Today's triggered breaks, current watchlist |
| **Charts** | `/docs/` | Auto-generated interactive chart (legacy, same HTML as before) |

The dashboard auto-refreshes every 60 seconds. All data comes from the REST API:

| Endpoint | Returns |
|---|---|
| `GET /api/system` | Scheduler running, next run times, job run history |
| `GET /api/portfolio` | Positions, equity, win rate, recent closed trades |
| `GET /api/signals` | Watchlist + today's triggered breaks |
| `POST /api/trades/close` | Manually close a position (paper mode only) |

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
| 10:30–16:00 every 15 min | 03:30–09:00 | `intraday_scan` |
| 16:15 | 09:15 | `review_scan` (fakeout check) |
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
# LINE (primary notification channel)
LINE_CHANNEL_ACCESS_TOKEN="your_token"
LINE_TO="your_user_or_group_id"
# LINE_MODE="broadcast"              # send to all followers instead

# Web app public URL (used in notification links)
APP_BASE_URL="https://your-service.up.railway.app"

# Trade mode
TRADE_MODE=paper                     # paper | live

# Postgres (Railway — persistent paper trades + job history)
DATABASE_URL="postgresql://..."

# SETTRADE OpenAPI
SETTRADE_APP_ID="your_app_id"
SETTRADE_APP_SECRET="your_app_secret"
SETTRADE_BROKER_ID="your_broker_id"
SETTRADE_APP_CODE="your_app_code"

# Optional — ops alerts only
DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."
```
