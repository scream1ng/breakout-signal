"""
Send representative dummy notifications through the configured channels.

Usage:
    py -3 test_notifications.py
"""

from datetime import datetime

from output.notifications import (
    send_eod_alert,
    send_intraday_alert,
    send_paper_trade_summary,
    send_paper_trade_update,
    send_review_alert,
)


CFG = {
    'capital': 100_000,
    'commission': 0.0015,
    'risk_pct': 0.005,
    'sl_mult': 1,
    'tp1_mult': 2,
    'tp2_mult': 4,
}


def build_intraday_signals():
    return [
        {
            'ticker': 'AAA.BK',
            'ticker_full': 'AAA.BK',
            'level': 12.5,
            'close': 12.9,
            'proj_rvol': 2.8,
            'cur_rvol': 2.1,
            'kind': 'Hz',
            'rsm': 86,
            'stretch': 1.8,
            'atr': 0.35,
            'criteria': 'Prime',
            'tl_angle': None,
        },
        {
            'ticker': 'BBB.BK',
            'ticker_full': 'BBB.BK',
            'level': 24.0,
            'close': 24.4,
            'proj_rvol': 1.9,
            'cur_rvol': 1.6,
            'kind': 'TL',
            'rsm': 74,
            'stretch': 4.5,
            'atr': 0.55,
            'criteria': 'STR',
            'tl_angle': 28,
        },
    ]


def build_review_signals():
    return [
        {
            'ticker': 'AAA.BK',
            'ticker_full': 'AAA.BK',
            'level': 12.5,
            'close': 12.2,
            'cur_rvol': 1.4,
            'kind': 'Hz',
            'rsm': 86,
            'stretch': 1.8,
            'criteria': 'Prime',
            'atr': 0.35,
            'tl_angle': None,
        }
    ]


def build_eod_signals():
    return [
        {
            'ticker': 'AAA.BK',
            'kind': 'hz',
            'bp': 12.5,
            'close': 12.95,
            'rvol': 2.2,
            'rsm': 86,
            'rvol_ok': True,
            'rsm_ok': True,
            'stretch': 1.8,
            'tl_angle': None,
        },
        {
            'ticker': 'CCC.BK',
            'kind': 'tl',
            'bp': 31.0,
            'close': 31.4,
            'rvol': 1.6,
            'rsm': 79,
            'rvol_ok': True,
            'rsm_ok': False,
            'stretch': 0.9,
            'tl_angle': 22,
        },
    ]


def build_recap(now):
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    return [
        {
            'ticker': 'AAA',
            'level': 12.5,
            'alerted_at': stamp,
            'status': 'HELD INTO CLOSE',
            'note': 'Still qualified in the EOD close scan.',
        },
        {
            'ticker': 'BBB',
            'level': 24.0,
            'alerted_at': stamp,
            'status': 'FALSE',
            'note': 'Closed back below level during the review pass.',
        },
        {
            'ticker': 'DDD',
            'level': 8.4,
            'alerted_at': stamp,
            'status': 'INTRADAY ONLY',
            'note': 'Did not qualify in the close scan.',
        },
    ]


def build_entry_events(now):
    stamp = now.isoformat(timespec='seconds')
    return [
        {
            'action': 'BUY',
            'ticker': 'AAA',
            'ticker_full': 'AAA.BK',
            'at': stamp,
            'price': 12.9,
            'shares': 700,
            'cash_after': 90_842.75,
            'net_value': 9_157.25,
            'criteria': 'Prime',
            'sl': 12.55,
            'tp1': 13.6,
            'tp2': 14.3,
        },
        {
            'action': 'BUY',
            'ticker': 'BBB',
            'ticker_full': 'BBB.BK',
            'at': stamp,
            'price': 24.4,
            'shares': 300,
            'cash_after': 83_513.77,
            'net_value': 7_328.98,
            'criteria': 'STR',
            'sl': 23.85,
            'tp1': 25.5,
            'tp2': 26.6,
        },
    ]


def build_exit_events(now):
    stamp = now.isoformat(timespec='seconds')
    return [
        {
            'action': 'SELL',
            'ticker': 'AAA',
            'ticker_full': 'AAA.BK',
            'at': stamp,
            'price': 12.2,
            'shares': 700,
            'cash_after': 92_000.11,
            'pnl': -595.14,
            'ret_pct': -5.43,
            'reason': 'FALSE_BREAKOUT',
        }
    ]


def build_summary():
    return {
        'capital': 100_000,
        'cash': 92_000.11,
        'realized_pnl': -595.14,
        'open_count': 1,
        'closed_count': 1,
        'positions': [
            {
                'ticker': 'BBB',
                'ticker_full': 'BBB.BK',
                'shares': 300,
                'entry_price': 24.4,
                'criteria': 'STR',
                'sl': 23.85,
                'tp1': 25.5,
                'tp2': 26.6,
            }
        ],
        'recent_closed': [
            {
                'ticker': 'AAA',
                'pnl': -595.14,
                'ret_pct': -5.43,
                'reason': 'FALSE_BREAKOUT',
            }
        ],
    }


def main():
    now = datetime.now()
    date_str = now.strftime('%Y_%m_%d')

    print('Sending dummy intraday alert...')
    send_intraday_alert(build_intraday_signals(), now, CFG)

    print('Sending dummy paper trade entry update...')
    send_paper_trade_update(build_entry_events(now), now, title='PAPER TRADE ENTRY')

    print('Sending dummy false breakout alert...')
    send_review_alert(build_review_signals(), now, CFG)

    print('Sending dummy paper trade exit update...')
    send_paper_trade_update(build_exit_events(now), now, title='PAPER TRADE EXIT')

    print('Sending dummy EOD alert...')
    send_eod_alert(
        build_eod_signals(),
        pending_list=[{'ticker': 'DDD.BK'}, {'ticker': 'EEE.BK'}],
        results=[],
        date_str=date_str,
        cfg=CFG,
        intraday_recap=build_recap(now),
    )

    print('Sending dummy paper trade summary...')
    send_paper_trade_summary(build_summary(), now.strftime('%Y-%m-%d'))

    print('Dummy notification run complete.')


if __name__ == '__main__':
    main()