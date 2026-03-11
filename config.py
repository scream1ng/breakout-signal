"""
config.py — Shared configuration for swing trader
==================================================
Edit this file to change settings across all scripts.
CLI arguments in main.py override these values when provided.

POSITION SIZING FORMULA:
    risk_amount = capital x risk_pct          (e.g. 100000 x 0.005 = 500)
    atr_pct     = ATR / entry_price           (e.g. ATR=2, price=100 -> 2%)
    sl_distance = entry_price x atr_pct x sl_atr_mult
    shares      = risk_amount / sl_distance
"""

CFG = {
    # TradingView market endpoint
    "tv_market": "thailand",

    # Benchmark for RS Rating calculation
    "benchmark": "^SET.BK",

    # yfinance ticker suffix for Thai stocks
    "ticker_suffix": ".BK",

    # Minimum daily turnover in THB to include a stock
    "min_turnover": 5_000_000,

    # RS filter thresholds
    "rs_rating_min":   70,
    "rs_momentum_min": 70,

    # Capital and risk per trade
    "capital":  100_000,
    "risk_pct":   0.005,   # 0.5 percent of capital per trade

    # Commission per side (0.15%)
    "commission": 0.0015,

    # Default chart period: 6mo, 12mo, 18mo, 2y
    "period": "12mo",

    # Money management multipliers
    "sl_atr_mult":   1,
    "tp1_atr_mult":  2,
    "tp2_atr_mult":  4,
    "be_after_days": 3,    # bars before SL moves to breakeven

    # Pivot Breakout strategy settings
    "psth_fast":   3,      # fast pivot strength — catches more, less confirmed
    "psth_slow":   7,      # slow pivot strength — fewer, stronger confirmed pivots
    "tick_size":   0.01,   # 1 tick above breakpoint for entry price

    # --- Entry quality filters (toggle independently for backtesting) ---
    "filter_no_reentry":  True,  # block re-entry at same level after SL/DayRej
    "filter_candle_body": True,  # require break candle body >= 50% of candle range

    "rvol_period": 20,     # lookback bars for relative volume
    "rvol_min":    1.5,    # min RVol to qualify as high-conviction break
}
