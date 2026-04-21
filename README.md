# BREAKOUT SCANNER — Swing Trading Scanner for Thai SET

Scans SET stocks daily for horizontal and trendline breakouts.
Filters by regime (above SMA50), relative volume, and RS Momentum.
Simulates trades with risk-based sizing, partial TP exits, and EMA10 trail.
Publishes an interactive HTML chart and backtest portfolio locally or to the cloud via Railway.

## PROJECT STRUCTURE

```text
swing_trader/
├── main.py                     ← single entry point (End of Day Scan)
├── intraday.py                 ← live trading hours scan
├── config.py                   ← your global settings (edit this)
├── requirements.txt            ← python dependencies
├── .env                        ← Webhooks & API keys (Never commit this!)
│
├── core/
│   ├── data.py                 ← download + cache price data
│   ├── settrade_client.py      ← SETTRADE API session logic
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
│   └── notifications.py        ← Discord webhook / Messaging sender
│
├── docs/
│   └── index.html              ← auto-generated HTML dashboard 
│
├── railway.json                ← Railway cloud configuration
├── server.py                   ← 24/7 web-server & automated scheduler
└── test_settrade.py            ← API Key verification script
```

---

## 🚀 Setup & Credentials

Before running the application, you must configure your `.env` file at the root of the project.

```ini
# Messaging Output
DISCORD_WEBHOOK="https://discord.com/api/webhooks/your-url-here"

# LINE Messaging API (optional)
LINE_CHANNEL_ACCESS_TOKEN="your_line_channel_access_token"
# Comma-separated LINE user/group/room IDs, or use LINE_USER_ID / LINE_GROUP_ID
LINE_TO="your_line_target_id"

# Public app URL for links in alerts (recommended on Railway)
APP_BASE_URL="https://your-service.up.railway.app"

# Railway Postgres (optional but recommended for persistent paper trades)
DATABASE_URL="postgresql://..."

# Data Provider (SETTRADE OpenAPI)
SETTRADE_APP_ID="your_app_id"
SETTRADE_APP_SECRET="your_app_secret"
SETTRADE_BROKER_ID="your_broker_id"
SETTRADE_APP_CODE="your_app_code"
```
*(Optionally run `python test_settrade.py` to verify your API connection works!)*

---

## 🛠 Commands

**`python main.py`**
Run End-of-Day scan. Prints breakout list to terminal and generates `docs/index.html`.

**`python intraday.py`**
Run live Intraday scan checking current prices against the generated watchlist.

**`python main.py --discord`**
Run scan and send the full ANSI-formatted Discord report. For intraday runs, the same flag also allows LINE paper-trade entry and exit updates when LINE is configured.

**`py -3 test_notifications.py`**
Send dummy messages through all notification functions now, using your current `.env` targets. This is the fastest way to preview tomorrow's LINE and Discord output before market open.

**`python main.py --view`**
Opens the interactive chart in the browser automatically.

**`python main.py --clear-cache`**
Forces deletion of locally cached `cache/` price data to trigger a fresh download.

### Options
You can combine flags to override `config.py` temporarily:
* `--period 2y` (lookback period)
* `--capital 200000` (starting capital)
* `--rsm 60` (min RS Momentum)

---

## ☁️ Railway Cloud Deployment (24/7 Automation)

This project is built to be deployed automatically to Railway, completely eliminating the need for complex GitHub Actions or frozen GitHub Pages.

1. Commit and push this entire repository to your GitHub.
2. In Railway, click **New** -> **Deploy from GitHub repository** and select this repo.
3. Once the environment builds, go to your new Railway Service's **Variables** tab and paste your `.env` secrets into the cloud:
   * `DISCORD_WEBHOOK`
   * `SETTRADE_APP_ID`, `SETTRADE_APP_SECRET`, `SETTRADE_BROKER_ID`, `SETTRADE_APP_CODE`
4. Go to **Settings** -> **Networking / Domains** and click **Generate Domain**. (Your Discord messages will automatically detect this domain and securely link to your charts).

**How it works:**
Railway spins up `server.py` in the background endlessly. It hosts your `docs/` folder entirely locally on the generated web domain (no GitHub Pages required), while a background Python scheduler actively drives your automated trading lifecycle:

* **Intraday Sniper (10:30–16:00 BKK):** Every 15 minutes, it runs `intraday.py` to catch live breakouts from the watchlist. Only **Prime** and **RVOL** signals trigger Discord alerts. A localized "Anti-Spam Memory" loop ensures you only ever get 1 notification per stock per day.
* **The Safety Net (16:15 BKK):** Runs a dedicated `intraday.py --review` fakeout check. If a stock broke out earlier but has now plunged back below its pivot, it sends a red "False Breakout" warning so you can instantly cut the position before the market closes.
* **The Analysis (16:45 BKK):** Runs the heavy `main.py` End-of-Day scan 15 minutes after market close. It re-evaluates the entire SET market mathematically, builds tomorrow's curated watchlist, fully regenerates your interactive HTML dashboard, and sends a daily wrap-up to Discord with all criteria (Prime / RVOL / RSM / STR / SMA50).

Paper trades are tracked in Railway Postgres automatically when `DATABASE_URL` is available. If not, the app falls back to `data/paper_portfolio.json` for local use.

## Notification Notes

- **Discord** receives all market alerts: intraday breakouts (Prime + RVOL only), false breakout warnings, and EOD summary (all criteria).
- **LINE** receives paper-trade updates only: BUY cards on Prime intraday entries, SELL cards on exits, and portfolio snapshot at EOD.
- Paper trades only open for **Prime** signals (RVOL ✓ + RSM ✓ + stretch ≤ 4). RVOL signals generate Discord alerts but do not open paper positions.
- **STR** (stretch > 4 = overextended) appears in EOD summary for awareness but never triggers intraday alerts or paper trades.
- If `LINE_MODE="broadcast"`, LINE sends to every account that added the bot. In that mode, `LINE_TO` is ignored.
- Every app-sent message is appended to `data/notification_outbox.jsonl` so you can inspect what the app sent.
