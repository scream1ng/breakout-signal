from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.entry import detect_pivots


CFG = {
    'rsm_min': 80,
    'rvol_min': 2.0,
}


def _df(highs: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            'High': highs,
            'Low': [7.5] * len(highs),
            'Close': closes,
            'SMA50': [8.0] * len(highs),
            'ATR': [0.5] * len(highs),
            'RSM': [90.0] * len(highs),
        },
        index=pd.date_range('2026-01-01', periods=len(highs), freq='D'),
    )


def test_detect_pivots_suppresses_same_bar_confirmed_breakout():
    df = _df(
        highs=[8.5, 9.0, 10.0, 9.8],
        closes=[8.2, 8.8, 9.5, 10.2],
    )
    rvol = np.array([1.0, 1.0, 1.0, 3.0])

    all_breaks, _, _, pending = detect_pivots(df, 1, rvol, CFG, 'TEST.BK')

    assert all_breaks == []
    assert pending == []


def test_detect_pivots_allows_breakout_after_prior_confirmation():
    df = _df(
        highs=[8.5, 9.0, 10.0, 9.8, 10.5],
        closes=[8.2, 8.8, 9.5, 9.7, 10.2],
    )
    rvol = np.array([1.0, 1.0, 1.0, 1.0, 3.0])

    all_breaks, _, _, pending = detect_pivots(df, 1, rvol, CFG, 'TEST.BK')

    assert len(all_breaks) == 1
    assert all_breaks[0]['bar'] == 4
    assert all_breaks[0]['bp'] == 10.0
    assert pending == []
