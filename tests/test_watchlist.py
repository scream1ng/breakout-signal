from __future__ import annotations

from app.core.watchlist import build_pending_info, merge_pending_levels


def test_merge_pending_levels_keeps_fast_and_slow_same_kind_levels():
    merged = merge_pending_levels(
        fast_levels=[
            {'kind': 'tl', 'level': 9.86, 'tl_angle': 27.5},
            {'kind': 'hz', 'level': 10.0},
        ],
        slow_levels=[
            {'kind': 'tl', 'level': 9.72, 'tl_angle': 18.0},
            {'kind': 'hz', 'level': 10.0},
        ],
    )

    assert merged == [
        {'kind': 'tl', 'level': 9.86, 'tl_angle': 27.5, 'source': 'fast'},
        {'kind': 'hz', 'level': 10.0, 'source': 'fast'},
        {'kind': 'tl', 'level': 9.72, 'tl_angle': 18.0, 'source': 'slow'},
    ]


def test_build_pending_info_keeps_surviving_levels():
    pending = [
        {'kind': 'hz', 'level': 0.73},
        {'kind': 'tl', 'level': 0.71, 'tl_angle': 18.5},
    ]

    info = build_pending_info(
        ticker='ETC.BK',
        desc='Earth Tech Environment Public Company Limited',
        sector='Utilities',
        pending_levels=pending,
        last_regime=True,
        last_close=0.75,
        last_atr=0.0229,
        rsm_last=79.7,
        rvol_last=3.58,
        last_avg_vol=12_345_678,
        last_sma50=0.68,
    )

    assert info is not None
    assert info['ticker'] == 'ETC.BK'
    assert info['levels'] == pending
    assert info['close'] == 0.75


def test_build_pending_info_requires_regime_and_levels():
    assert build_pending_info(
        ticker='ETC.BK',
        desc='Earth Tech Environment Public Company Limited',
        sector='Utilities',
        pending_levels=[],
        last_regime=True,
        last_close=0.75,
        last_atr=0.0229,
        rsm_last=79.7,
        rvol_last=3.58,
        last_avg_vol=12_345_678,
        last_sma50=0.68,
    ) is None

    assert build_pending_info(
        ticker='ETC.BK',
        desc='Earth Tech Environment Public Company Limited',
        sector='Utilities',
        pending_levels=[{'kind': 'hz', 'level': 0.73}],
        last_regime=False,
        last_close=0.75,
        last_atr=0.0229,
        rsm_last=79.7,
        rvol_last=3.58,
        last_avg_vol=12_345_678,
        last_sma50=0.68,
    ) is None
