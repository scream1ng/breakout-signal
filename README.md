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
Run scan and push the alerts instantly to Discord. (Works with intraday too: `python intraday.py --discord`)

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

* **Intraday Sniper (10:30–16:00 BKK):** Every 15 minutes, it runs `intraday.py` to catch live breakouts from the watchlist and instantly sends highly detailed ProjRVol alerts to Discord. A localized "Anti-Spam Memory" loop ensures you only ever get 1 notification per stock per day.
* **The Safety Net (16:15 BKK):** Runs a dedicated `intraday.py --review` Fakeout Check. If a stock broke out earlier but has now plunged back below its pivot, it sends a red "Failed Breakout" warning so you can instantly cut the position before the market closes.
* **The Analysis (18:00 BKK):** Runs the heavy `main.py` End-of-Day scan. It re-evaluates the entire SET market mathematically, builds tomorrow's curated watchlist, fully regenerates your interactive HTML dashboard, and beams a daily wrap-up straight to your phone.
