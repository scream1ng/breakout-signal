# Operations Guide — Breakout Signal Dashboard

Complete guide to understanding what each script does, when they run, and how to monitor the system.

---

## 🎯 System Overview

```
┌─────────────────────────────────────────────────────────┐
│  APScheduler (Background Job Runner)                    │
│  app/scheduler/runner.py + app/scheduler/jobs.py        │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   ┌─────────┐          ┌──────────┐
   │ main.py │          │intraday.py
   │ (EOD)   │          │(15-min)
   └────┬────┘          └────┬─────┘
        │                     │
        ├─► Scan ALL ~600 SET stocks
        ├─► Download OHLCV data (cache)
        ├─► Detect breakouts (pivots + trendlines)
        ├─► Calculate RS Momentum + volume
        ├─► Filter & rank by criteria
        ├─► Generate chart HTML
        ├─► Send Discord alerts + LINE paper-trade notifications
        └─► Store results in watchlist.json
        
┌──────────────────────────────────────────────────────────┐
│  FastAPI Web Server (main_app.py)                        │
│  Serves dashboard + REST API                             │
│  ├─ GET / → Dashboard tab (jobs, history)                │
│  ├─ GET /portfolio → Portfolio tab (positions, P&L)      │
│  ├─ GET /signals → Signals tab (watchlist, alerts)       │
│  └─ GET /chart → Interactive chart view                  │
└──────────────────────────────────────────────────────────┘
```

---

## 📅 Scheduled Jobs

### **1. EOD Scan** (`main.py`)

**Schedule:** Daily at **17:30** BKT (Market close)

**What it does:**
1. Fetch OHLCV for all ~600 SET stocks (yfinance → SETTRADE fallback)
2. Detect horizontal + trendline breakouts (entry pivots)
3. Calculate RS Momentum vs ^SET.BK benchmark
4. Rank by breakout strength: Prime > STR > RVOL > RSM > SMA50
5. Filter by volume + momentum thresholds
6. Save **watchlist.json** (tomorrow's opportunities)
7. Generate **docs/index.html** (interactive chart)
8. Send Discord notification: EOD summary table with all close-qualified signals
9. Send LINE paper-trade summary: portfolio snapshot + recent trade history

**Key outputs:**
- `data/watchlist.json` — Tomorrow's scan list (grouped by criteria)
- `docs/index.html` — Interactive chart with breakouts highlighted
- Discord embed with full metrics table (ticker, level, price, criteria, RVOL, RSM, STR)
- LINE portfolio snapshot and trade-history messages

**Important behavior:**
- EOD is a fresh full-market close scan.
- An intraday fire from yesterday's watchlist should appear in today's EOD output only if it still qualifies on the final daily close.
- EOD shows all stocks that qualify at the close, not every intraday touch from the session.

**Example signal entry:**
```json
{
  "ticker": "SMT.BK",
  "kind": "Hz",
  "level": 1.60,
  "close": 1.60,
  "rvol": 7.8,
  "rsm": 89,
  "stretch": 3.7,
  "filter_type": "Prime"
}
```

---

### **2. Intraday Scan** (`intraday.py`)

**Schedule:** Every **15 minutes** (09:30–16:30 BKT, market hours only)

**What it does:**
1. Fetch live prices for all stocks in **watchlist.json**
2. Check if any have closed above their breakout level
3. Flag new breakouts, fakeouts (false breaks), and extended moves (STR > 4x)
4. Send Discord alerts for live breakouts detected from yesterday's watchlist
5. Send Discord alerts for fakeout review at 16:15
6. Send LINE notifications only when a paper-trade entry or exit is created

**Key outputs:**
- Discord embeds for intraday breakout and fakeout alerts
- Paper trade entries (if `TRADE_MODE=paper`)
- LINE trade entry / exit messages

**Alert types:**
- ✅ **Breakout detected** → Signal triggered above level
- ⚠️ **Fakeout** → Closed below level after near miss
- 🚀 **Overextended** → STR > 4.0x (risk warning)

---

### **3. Paper Trade Update** (Continuous, triggered by intraday scan)

**Schedule:** Every 15 minutes when a signal is processed

**What it does:**
1. Open position if signal closes above level + breakout threshold
2. Set stop-loss at breakout level - (% slippage)
3. Set take-profit targets at 1.5x, 2.0x, 2.5x risk-reward
4. Close positions on SL hit, TP hit, or EMA10 exit
5. Track P&L and trade metrics

**Key outputs:**
- LINE trade entry/exit notifications
- Paper trade ledger (data/paper_trades.jsonl or PostgreSQL)
- Portfolio P&L updated in real-time

---

### **4. EOD Portfolio Summary** (`main.py` → portfolio update)

**Schedule:** Daily at **17:15** BKT (pre-close)

**What it does:**
1. Calculate total portfolio metrics (cash, equity, open positions, daily P&L)
2. Close any positions still open at 16:30 (market close)
3. Send LINE portfolio snapshot
4. Archive results to database

**Key outputs:**
- LINE portfolio message: "📊 Portfolio summary — Cash: X, Equity: Y, P&L: Z"
- Trade history and monthly summary

---

## 🖥️ Dashboard Tabs (FastAPI Frontend)

### **Tab 1: Dashboard**
📍 **GET /** 

Shows system health and job execution history:
- ✅ Job status (last run, duration, success/failure)
- 📊 Job history (recent runs with timestamps)
- ⏱️ Next scheduled runs (countdown timers)
- 🚨 Any errors or warnings

**UI Components:**
- Job execution timeline (green = success, red = error)
- Duration graphs (showing job runtimes over time)
- Error log viewer (click to expand error details)

---

### **Tab 2: Portfolio**
📍 **GET /portfolio**

Your trading positions and performance:
- 💰 Cash balance
- 📈 Open positions (ticker, entry, current, P&L, %)
- 📊 Closed trades (history, win rate, risk-reward)
- 📉 Daily/monthly summary (return %, win rate, max loss)

**UI Components:**
- Position cards (click to view entry details, exit reason)
- Trade history table (sortable by date, P&L, type)
- Portfolio metrics summary (top stats)

---

### **Tab 3: Signals**
📍 **GET /signals**

Today's active signals and watchlist:
- 🎯 Live breakouts (updating every 15 min)
- 📋 Watchlist detail (all scanned stocks, criteria, metrics)
- 📌 Grouped by criteria (Prime, STR, RVOL, RSM, SMA50)

**UI Components:**
- Signal carousel (swipe through active breakouts)
- Watchlist grouping (expandable by criteria type)
- Real-time price updates (Live badge with countdown to next scan)

---

### **Tab 4: Chart**
📍 **GET /docs/**

Interactive chart view:
- 📊 Generated by `output/chart_combined.py` (post-EOD scan)
- 🕯️ Lightweight Charts candles (SET stocks)
- 📍 Breakout levels marked + highlighted
- 💎 Criteria-specific color badges (Prime=blue, STR=red, RVOL=green, RSM=orange, SMA50=gray)

**UI Components:**
- Candle chart (drag to zoom, hover for OHLCV)
- Breakout sidebar (click to jump to stock)
- Criteria filter (toggle to show/hide by type)

---

## 📱 Notification Channels

### **LINE**
- ✅ Paper trade entries / exits
- ✅ Portfolio snapshots (daily at close)
- ✅ Trade summaries (when position closed)

**Message Format:**
```
💼 PAPER TRADE ENTRY
SMT.BK 3,000 sh @ 1.60 BT
Stop: 1.58 BT | TP1: 1.64 BT | TP2: 1.68 BT
Proj RVol: 2.8x | RSM: 89
```

### **Discord**
- ✅ Intraday breakout alerts
- ✅ Fakeout alerts (false breakouts only)
- ✅ EOD summary embed (full metrics table)
- ✅ Job failures (scheduler errors, data fetch failures)
- ✅ System alerts (warnings, configuration issues)

**Message Format:**
```
▲ Live breakout signals · 3 stocks · 14:25 BKK
TICKER   LEVEL    PRICE    TYPE      CRITERIA
SMT      1.60     1.60     Hz        Prime
KKP      82.50    82.50    Trendline RSM
TEAM     3.48     3.48     Hz        STR
```

---

## 🔄 Data Flow

### **Morning (Overnight)**
```
23:00 ← System checks logs for any errors from previous EOD
```

### **Market Open (09:30)**
```
09:30 ← Intraday scanner starts (15-min intervals)
       ├─ Fetch live prices for yesterday's watchlist
       ├─ Check for new breakouts or fakeouts
      └─ Send Discord alerts + open paper trades
```

### **Throughout Day (09:30–16:30)**
```
09:45, 10:00, 10:15, ... 16:15, 16:30
  ↓ Every 15 min
  ├─ Update watchlist vs live prices
  ├─ Close any positions on SL/TP/EMA10 exits
  ├─ Send trade updates
  └─ Update dashboard in real-time
```

### **Market Close (16:30)**
```
16:30 ← Intraday scanner stops
       ├─ Force-close any remaining paper positions
       └─ Send portfolio summary to LINE
```

### **EOD Scan (17:30)**
```
17:30 ← EOD scan runs (main.py)
       ├─ Download day's OHLCV
       ├─ Detect new breakouts (for tomorrow)
       ├─ Generate chart + watchlist.json
      ├─ Send Discord EOD summary
      └─ Send LINE paper-trade summary
       └─ Update dashboard with new signals
       
18:00 ← Ready for tomorrow's intraday scans
```

---

## 🛠️ Deployment to Railway

### **Production Checklist**

Before deploying to Railway, verify:

✅ All scripts run locally without errors
✅ Smoke tests pass: `py -m pytest -q tests/test_api_smoke.py`
✅ Integration tests pass:
  - `py -m tests.test_settrade` (data fetch OK)
  - `py -m tests.test_notifications` (Discord alerts + LINE paper-trade sends OK)

✅ SETTRADE credentials in `.env` (not committed to git)
✅ LINE token in `.env` (not committed to git)
✅ Discord webhook in `.env` (if using ops alerts)

✅ PostgreSQL database configured (Railway: project → Add Plugin → PostgreSQL)
✅ Railway config in `.env`:
  ```
  DATABASE_URL=postgresql://user:pass@host:5432/db
  RAILWAY_PUBLIC_DOMAIN=your-service.up.railway.app
  ```

### **Deploy Steps**

1. **Push to main branch:**
   ```bash
   git add -A
   git commit -m "Production readiness: align Discord table, add OPERATIONS.md"
   git push origin main
   ```

2. **Railway auto-deploys** (webhook trigger)
   - Watch Railway dashboard for build/deploy progress
   - Check logs: `Railway CLI → logs --follow`

3. **Verify on Railway:**
   - Dashboard loads: `https://your-service.up.railway.app/`
   - API responds: `curl https://your-service.up.railway.app/api/signals`
  - First EOD scan runs at 17:30 BKT (check Discord summary + LINE paper-trade summary)
  - Intraday scans start at 09:30 BKT tomorrow (check Discord alerts)

4. **Monitor first 48 hours:**
   - Check scheduler job history in dashboard
  - Verify notifications arrive on the expected channel (Discord alerts, LINE paper-trade)
   - Watch for data errors in railway logs
   - Manual override available: trigger `main.py` via `/api/scan` endpoint if needed

---

## ⚙️ Configuration

All settings in `config.py` and `app/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `BREAKOUT_MIN_RANGE` | 2.0% | Minimum pivot range to qualify as breakout |
| `RVOL_MIN` | 1.5x | Volume threshold for RVOL filter |
| `RS_MOMENTUM_MIN` | 70 | RSM threshold vs ^SET.BK |
| `PAPER_TRADE_PCT_SIZE` | 1.0% | Position size as % of portfolio |
| `TRADE_MODE` | "paper" | "paper" (simulated) or "live" (SETTRADE orders) |
| `MAX_OPEN_POSITIONS` | 5 | Max concurrent paper trades |

---

## 🚀 Quick Start

### **Local Development**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up .env
cp .env.example .env
# Edit .env with SETTRADE credentials, LINE token, etc.

# 3. Run tests
py -m pytest -q tests/test_api_smoke.py

# 4. Start server (with scheduler)
python main_app.py
# Visit http://localhost:8080/

# 5. Manual EOD scan
python main.py

# 6. Manual intraday scan
python intraday.py
```

### **Production (Railway)**

```bash
# 1. Push to main → Railway auto-deploys
git push origin main

# 2. Monitor
curl https://your-service.up.railway.app/api/signals

# 3. Check logs
railway logs --follow
```

---

## 📊 Monitoring & Troubleshooting

### **Common Issues**

| Issue | Cause | Fix |
|-------|-------|-----|
| "Can't subtract datetimes" | Naive/aware timezone mismatch | ✅ Fixed in `app/scheduler/runner.py` |
| Duplicate tickers in watchlist | Data-shape variants (list vs dict) | ✅ Fixed in `app/api/scan.py` |
| `/api/signals` crashes | Watchlist stored as plain list | ✅ Fixed in `app/api/signals.py` |
| Dashboard slow | Too many open trades | Reduce `MAX_OPEN_POSITIONS` |
| No notifications | Discord/LINE tokens missing | Check `.env` and Railway config |
| Charts not updating | HTML generator crashed | Check `output/chart_combined.py` logs |

### **Debug Mode**

Enable verbose logging:
```bash
export LOG_LEVEL=DEBUG
python main_app.py
```

Check logs:
- Local: `app/logs/` directory
- Railway: `railway logs --follow`

---

## 🎓 Learning Resources

- **Pivot Detection:** See [app/core/entry.py](app/core/entry.py) for horizontal + trendline breakout logic
- **RS Momentum:** See [app/core/rsm.py](app/core/rsm.py) for benchmark calculation
- **Paper Trading:** See [app/core/paper_trade.py](app/core/paper_trade.py) for position management
- **Notifications:** See [app/notifications/](app/notifications/) for LINE/Discord formatting
- **Scheduler:** See [app/scheduler/](app/scheduler/) for job execution + error tracking

---

## ✅ You're Ready!

This system is **production-ready** for Railway deployment. All runtime bugs are fixed, tests pass, and documentation is complete. Deploy with confidence! 🚀
