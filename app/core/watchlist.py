"""
watchlist.py
Helpers for turning still-active levels into next-session watchlist rows.
"""


def _level_key(level: dict) -> tuple:
    """Stable key for de-duping the same pending line from fast/slow scans."""
    kind = str(level.get('kind', '')).lower()
    price = round(float(level.get('level', 0) or 0), 4)
    angle = level.get('tl_angle')
    angle_key = round(float(angle), 1) if angle is not None else None
    return kind, price, angle_key


def merge_pending_levels(
    fast_levels: list[dict],
    slow_levels: list[dict],
) -> list[dict]:
    """
    Keep all distinct pending levels from fast and slow pivot scans.

    Older code keyed only by `kind`, so a fast HZ/TL could overwrite a slow
    HZ/TL for the same ticker and never reach the intraday watchlist.
    """
    merged = []
    seen = set()

    for source, levels in (('fast', fast_levels), ('slow', slow_levels)):
        for item in levels or []:
            row = dict(item)
            row['source'] = source
            key = _level_key(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)

    return merged


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
