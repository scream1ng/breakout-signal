# BREAKOUT SCANNER — Swing Trading Scanner for Thai SET

Scans SET stocks daily for horizontal and trendline breakouts.
Filters by regime (above SMA50), projected relative volume, and RS Momentum.
Simulates trades with risk-based sizing, partial TP exits, and EMA10 trail stop.
Publishes an interactive HTML chart and backtest portfolio locally or to Railway cloud.

---

## PROJECT STRUCTURE

```text
breakout-signal/
├── main.py                     ← EOD scan entry point
├── intraday.py                 ← live intraday scanner (runs every 15 min on Railway)
├── server.py                   ← Railway: HTTP server + automated job scheduler
├── config.py                   ← global settings (edit this)
├── requirements.txt
├── .env                        ← secrets — NEVER commit
├── test_notifications.py       ← send dummy messages to verify Discord + LINE format
│
├── core/
│   ├── data.py                 ← price download + daily cache
│   ├── settrade_client.py      ← SETTRADE OpenAPI session
│   ├── entry.py                ← pivot detection (horizontal + trendline breakouts)
│   ├── exit.py                 ← backtest trade simulator (SL/TP/BE/EMA10)
│   ├── paper_trade.py          ← live paper trade ledger (Postgres or JSON)
│   ├── portfolio.py            ← cash-aware backtest portfolio
│   ├── rsm.py                  ← RS Momentum vs benchmark
│   └── scanner.py              ← TradingView pre-screen (SET universe)
│
├── output/
│   ├── chart_interactive.py    ← per-stock chart data builder
│   ├── chart_combined.py       ← combined HTML dashboard (chart + backtest + portfolio)
│   ├── report.py               ← terminal output (ANSI colours)
│   └── notifications.py        ← all Discord + LINE notification logic
│
├── docs/
│   └── index.html              ← auto-generated HTML dashboard (served by Railway)
│
└── data/
    ├── watchlist.json          ← pending breakout levels for next session
    ├── alert_state.json        ← intraday anti-spam state (resets daily)
    ├── paper_portfolio.json    ← paper trade state (fallback when no Postgres)
    └── notification_outbox.jsonl ← log of every sent notification
```

---

## CRITERIA SYSTEM

Signals are classified into one label (highest priority wins):

| Label | Condition | Intraday alert | Paper trade |
|---|---|---|---|
| **Prime** | proj_rvol ≥ MIN_RVOL **and** RSM ≥ MIN_RSM **and** stretch ≤ 4 | ✓ Discord | ✓ Opens position |
| **RVOL** | proj_rvol ≥ MIN_RVOL, RSM below threshold | ✓ Discord | — |
| **RSM** | RSM ≥ MIN_RSM, proj_rvol below threshold | — | — |
| **SMA50** | Above SMA50 only | — | — |
| **STR** | stretch > 4 (overextended) | — | — EOD info only |

> Intraday uses **projected RVol** (not current RVol) — projects full-day volume based on time elapsed in SET session (10:00–12:30 + 14:00–16:30 = 300 min).

---

## PAPER TRADE SYSTEM

Positions open on **Prime** signals only. Size formula: `capital × risk_pct / (ATR × sl_mult)`

Exit strategy (mirrors backtest — checked every intraday scan):

| Exit | Trigger | Action |
|---|---|---|
| **TP1** | close ≥ entry + 2×ATR | Sell 30% at TP1 price |
| **Breakeven** | after `be_days` (3) days | Move SL to entry price |
| **TP2** | close ≥ entry + 4×ATR | Sell ~30% of remaining at TP2 price |
| **EMA10 trail** | close < EMA10 | Exit remaining ~40% at close |
| **SL** | close ≤ stop loss | Exit remaining at close |
| **False breakout** | 16:15 review: close < pivot | Exit all at close |

Storage: Railway Postgres when `DATABASE_URL` set, else `data/paper_portfolio.json`.

---

## LINE NOTIFICATION CARDS

All paper trade events send a Flex Message bubble to LINE:

| Card | Triggered by |
|---|---|
| **Open** | Prime signal entry — shows entry price, shares, value, RVol/RSM/STR |
| **TP1** | Price hits TP1 — shows tranche P&L, shares remaining, next TP target |
| **TP2** | Price hits TP2 — shows tranche P&L, shares remaining, trail/SL level |
| **Close** | EMA10 trail / SL / BE / false breakout — colored green/red by profit |
| **History** | EOD — table of last 10 closed trades, win rate, avg win/loss |
| **Portfolio** | EOD — total equity, cash, realized P&L, open count |

---

## DISCORD NOTIFICATIONS

| Message | Time (BKK) | Content |
|---|---|---|
| **Intraday** | 10:30–16:00 every 15 min | Yellow embed — Prime + RVOL breakouts only |
| **Fakeout** | 16:15 | Red embed — stocks that failed below pivot |
| **EOD** | 16:45 | Green embed — all criteria (Prime/RVOL/RSM/STR/SMA50) with 🟢🔴 RVOL/RSM/STR |

RVOL/RSM icons: 🟢 ≥ threshold, 🔴 below. STR: 🟢 ≤ 4.0, 🔴 > 4.0 (overextended).

---

## COMMANDS

```bash
# EOD scan — print results + generate docs/index.html
python main.py

# EOD scan + send Discord alert + LINE portfolio/history summary
python main.py --discord

# Intraday scan — check watchlist against current prices (print only)
python intraday.py

# Intraday scan + send Discord + LINE paper trade updates
python intraday.py --discord

# Fakeout review — check alerted stocks for false breakouts
python intraday.py --discord --review

# Open interactive chart in browser
python main.py --view

# Open chart for one stock
python main.py --view TOP

# Send test notifications to verify Discord + LINE format
py -3 test_notifications.py

# Clear cached price data
python main.py --clear-cache
```

Override config temporarily:
```bash
python main.py --period 2y --capital 200000 --rsm 60
```

---

## RAILWAY DEPLOYMENT (24/7 Automation)

1. Push repo to GitHub
2. Railway → **New** → **Deploy from GitHub repo**
3. Set **Variables** in Railway dashboard:
   - `DISCORD_WEBHOOK`
   - `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_TO` (or `LINE_MODE=broadcast`)
   - `SETTRADE_APP_ID`, `SETTRADE_APP_SECRET`, `SETTRADE_BROKER_ID`, `SETTRADE_APP_CODE`
   - `DATABASE_URL` (Postgres — for persistent paper trades)
   - `APP_BASE_URL` (your Railway domain — for chart links in messages)
4. **Settings → Networking → Generate Domain**

**Automated schedule (server.py):**

| Time (BKK) | UTC | Job |
|---|---|---|
| 10:30–16:00 every 15 min | 03:30–09:00 | `intraday.py --discord` |
| 16:15 | 09:15 | `intraday.py --discord --review` |
| 16:45 | 09:45 | `main.py --discord` (EOD) |

> Schedule runs in UTC internally. Server also runs a full EOD scan on startup to ensure dashboard exists after any redeploy.

---

## SETUP (.env file)

```ini
# Discord
DISCORD_WEBHOOK="https://discord.com/api/webhooks/your-url"

# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN="your_token"
LINE_TO="your_user_or_group_id"       # comma-separated for multiple
# LINE_MODE="broadcast"               # send to all followers instead

# Railway public URL (for chart links in messages)
APP_BASE_URL="https://your-service.up.railway.app"

# Postgres (Railway — persistent paper trades)
DATABASE_URL="postgresql://..."

# SETTRADE OpenAPI (primary data source)
SETTRADE_APP_ID="your_app_id"
SETTRADE_APP_SECRET="your_app_secret"
SETTRADE_BROKER_ID="your_broker_id"
SETTRADE_APP_CODE="your_app_code"
```

Run `py -3 test_settrade.py` to verify SETTRADE connection.
Run `py -3 test_notifications.py` to verify all Discord + LINE cards.
