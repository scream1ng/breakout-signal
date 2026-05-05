"""
watchlist.py
Helpers for turning still-active levels into next-session watchlist rows.
"""


def build_pending_info(
    *,
    ticker: str,
    desc: str,
    sector: str,
    pending_levels: list[dict],
    last_regime: bool,
    last_close: float,
    last_atr: float,
    rsm_last: float,
    rvol_last: float,
    last_avg_vol: float,
    last_sma50: float,
):
    """
    Return watchlist payload for levels that remain active into the next session.

    `detect_pivots()` already removes lines that were actually broken on the
    current bar, so any level left in `pending_levels` is still valid even if
    another line in the same ticker fired today.
    """
    if not pending_levels or not last_regime:
        return None

    return dict(
        ticker=ticker,
        desc=desc,
        sector=sector,
        close=last_close,
        atr=round(last_atr, 4),
        rsm=round(rsm_last, 1),
        rvol=rvol_last,
        avg_volume=round(last_avg_vol),
        sma50=round(last_sma50, 4),
        levels=pending_levels,
    )
