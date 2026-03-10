SWING TRADER — Thai SET Scanner
================================

FOLDER STRUCTURE
----------------
swing_trader/
├── config.py         ← edit settings here (capital, risk, RS thresholds)
├── main.py           ← single stock chart + backtest
├── scan.py           ← full SET scan with RS filter + leaderboard
├── requirements.txt  ← dependencies
├── charts/           ← all PNG charts saved here automatically
└── logs/             ← trade logs (future)


INSTALL (one time)
------------------
pip install -r requirements.txt


HOW TO RUN
----------

1. SINGLE STOCK — chart + backtest for one ticker:

   python main.py KBANK.BK
   python main.py DELTA.BK --period 2y
   python main.py CPALL.BK --period 18mo --capital 200000

2. FULL SET SCAN — all stocks, RS filter, leaderboard:

   python scan.py
   python scan.py --period 2y
   python scan.py --rs-rating 80 --rs-momentum 80
   python scan.py --min-turnover 50000000
   python scan.py --capital 200000 --risk-pct 0.02

   Output: individual charts in charts/ + terminal leaderboard


STRATEGIES
----------
1. MA Crossover      EMA10 crosses above EMA20
                     Green arrow = BUY
                     Exit = EMA10 cross down or SL

2. BB Squeeze        Bollinger Bands narrow (squeeze) then
                     price breaks above upper band
                     Cyan arrow = BUY
                     Exit = price closes below BB midline or SL

3. S/R Breakout      Price closes above horizontal resistance
                     on above-average volume
                     Gold arrow = BUY
                     Exit = EMA10 close below or SL


HARD RULES (applied to ALL strategies)
---------------------------------------
• Entry ONLY when Close > SMA50
• RS Rating > 75 (scan.py only)
• RS Momentum > 75 (scan.py only)


MONEY MANAGEMENT (same for all strategies)
------------------------------------------
• Position size : risk 1% of capital per trade
• Stop Loss     : Entry − 1×ATR  (red dashed line on chart)
• After 3 days  : SL moves to breakeven (orange dashed line)
• TP1           : Entry + 2×ATR → exit 30% of position (★ star on chart)
• TP2           : Entry + 4×ATR → exit 30% of position (★ star on chart)
• Final exit    : Remaining 40% exits when Close < EMA10


CHART READING
-------------
Arrows:
  ↑ Green  MA BUY       MA cross entry
  ↑ Cyan   BB BUY       BB squeeze breakout entry
  ↑ Gold   SR BUY       S/R breakout entry
  ↓ Red    xxx SL       Stopped out
  ↓ Orange xxx EMA10    Exited on EMA10 close
  ↓ Grey   xxx End      Still open at end of data

Lines:
  Red dashed    = Stop Loss level
  Orange dashed = Breakeven SL (after 3 days)
  Light green   = TP1 target
  Bright green  = TP2 target
  ★ Star        = TP actually hit

MAs:
  Teal solid    = EMA10
  Yellow dashed = EMA20
  Red bold      = SMA50
  Red faint     = SMA200

Middle panel (BB Width):
  RED shading   = Squeeze active (bands very narrow)
  Watch for BB↑ arrows after red zones


EXIT REASONS ON ARROWS
-----------------------
  MA SL    → MA cross trade stopped out at SL
  MA EMA10 → MA cross trade exited when Close < EMA10
  BB SL    → BB squeeze trade stopped out
  BB EMA10 → BB squeeze trade EMA10 exit
  SR SL    → S/R breakout stopped out
  SR EMA10 → S/R breakout EMA10 exit


SETTINGS
--------
Edit config.py to permanently change:
  capital, risk_pct, rs_rating_min, rs_momentum_min,
  min_turnover, sl_atr_mult, tp1_atr_mult, tp2_atr_mult,
  be_after_days, benchmark, period