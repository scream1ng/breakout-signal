from __future__ import annotations

from app.core.watchlist import build_pending_info


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
