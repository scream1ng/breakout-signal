"""
asx/config_asx.py — ASX configuration
"""

CFG = {
    # TradingView market endpoint
    "tv_market": "australia",

    # Benchmark for RS Momentum calculation
    "benchmark": "^AXJO",

    # yfinance ticker suffix
    "ticker_suffix": ".AX",

    # Minimum daily turnover in AUD
    "min_turnover": 500_000,

    # RS filter thresholds
    "rs_rating_min":   70,
    "rs_momentum_min": 70,

    # Capital and risk per trade
    "capital":  10_000,
    "risk_pct":   0.005,   # 0.5% per trade

    # Commission per side (0.1% typical ASX broker)
    "commission": 0.001,

    # Default chart period
    "period": "12mo",

    # Money management multipliers
    "sl_atr_mult":   1,
    "tp1_atr_mult":  2,
    "tp2_atr_mult":  4,
    "be_after_days": 3,
    "min_atr_pct":   2.5,

    # Pivot Breakout strategy settings
    "psth_fast":   3,
    "psth_slow":   7,

    # Entry quality filters
    "filter_no_reentry":  True,
    "filter_candle_body": True,

    "rvol_period": 20,
    "rvol_min":    1.5,
}