"""
app/notifications/line.py — LINE Flex Messages (primary notification channel)
==============================================================================
Phase 4: LINE now receives ALL signal types that previously went to Discord.

Public API
----------
  send_intraday_alert(signals, now, cfg)    — live breakout carousel
  send_review_alert(signals, now, cfg)      — fakeout warning bubble
  send_eod_alert(today, pending, results, date_str, cfg)  — EOD summary
  send_trade_update(events, now, cfg)       — paper trade BUY/SELL bubbles
  send_portfolio_summary(summary, date_label)             — portfolio snapshot
  send_trade_history(closed_trades, n=10)                 — trade history table
"""

import logging
import os
import time
from datetime import datetime

import requests

from app.config import LINE_TOKEN, LINE_MODE, LINE_TARGETS, APP_BASE_URL, TRADE_CFG

logger = logging.getLogger(__name__)

MAX_STR = 4.0   # stretch > 4.0 → overextended

# ── Low-level send helpers ────────────────────────────────────────────────────

def _push(target: str, messages: list) -> bool:
    try:
        r = requests.post(
            'https://api.line.me/v2/bot/message/push',
            headers={'Authorization': f'Bearer {LINE_TOKEN}', 'Content-Type': 'application/json'},
            json={'to': target, 'messages': messages},
            timeout=10,
        )
        if r.status_code != 200:
            logger.warning('LINE push %s error %s: %s', target, r.status_code, r.text[:120])
            return False
        return True
    except Exception as exc:
        logger.warning('LINE push failed: %s', exc)
        return False


def _broadcast(messages: list) -> bool:
    try:
        r = requests.post(
            'https://api.line.me/v2/bot/message/broadcast',
            headers={'Authorization': f'Bearer {LINE_TOKEN}', 'Content-Type': 'application/json'},
            json={'messages': messages},
            timeout=10,
        )
        if r.status_code != 200:
            logger.warning('LINE broadcast error %s: %s', r.status_code, r.text[:120])
            return False
        return True
    except Exception as exc:
        logger.warning('LINE broadcast failed: %s', exc)
        return False


def _send(label: str, messages: list) -> bool:
    if not LINE_TOKEN:
        logger.debug('LINE token not configured — skipping %s', label)
        return False

    if LINE_MODE == 'broadcast':
        ok = _broadcast(messages)
        time.sleep(0.4)
        return ok

    if not LINE_TARGETS:
        logger.debug('No LINE targets configured — skipping %s', label)
        return False

    ok = True
    for target in LINE_TARGETS:
        if not _push(target, messages):
            ok = False
        time.sleep(0.4)
    return ok


# ── Flex component helpers ────────────────────────────────────────────────────

def _ltext(text, color='#222222', size='sm', weight='regular', flex=None, align='start') -> dict:
    obj = {'type': 'text', 'text': str(text), 'color': color,
           'size': size, 'weight': weight, 'align': align}
    if flex is not None:
        obj['flex'] = flex
    return obj


def _lrow(label: str, value: str, value_color: str = '#222222') -> dict:
    return {
        'type': 'box', 'layout': 'horizontal', 'margin': 'xs',
        'contents': [
            _ltext(label, color='#888888', size='sm', flex=3),
            _ltext(value, color=value_color, size='sm', weight='bold', flex=4, align='end'),
        ],
    }


def _lsep() -> dict:
    return {'type': 'separator', 'color': '#EEEEEE', 'margin': 'sm'}


def _lheader(title: str, subtitle: str, bg_color: str) -> dict:
    return {
        'type': 'box', 'layout': 'vertical',
        'paddingAll': '12px', 'paddingBottom': '8px',
        'backgroundColor': bg_color,
        'contents': [
            _ltext(title,    color='#FFFFFF', size='sm', weight='bold'),
            _ltext(subtitle, color='#FFFFFF99', size='xs'),
        ],
    }


def _lbtn(label: str, url: str) -> dict:
    return {
        'type': 'box', 'layout': 'vertical', 'paddingAll': '0px',
        'contents': [{
            'type': 'button',
            'action': {'type': 'uri', 'label': label, 'uri': url},
            'color': '#00b900', 'style': 'primary', 'height': 'sm',
        }],
    }


def _metric_color(value, threshold, invert=False) -> str:
    try:
        passes = float(value) <= threshold if invert else float(value) >= threshold
    except Exception:
        passes = False
    return '#00b900' if passes else '#e03131'


def _fmt(v, d=2) -> str:
    try:
        return f'{float(v):.{d}f}'
    except Exception:
        return '—'


def _criteria_label(sig: dict) -> str:
    stretch = float(sig.get('stretch', 0) or 0)
    rvol_ok = bool(sig.get('rvol_ok', False))
    rsm_ok  = bool(sig.get('rsm_ok', False))
    if stretch > MAX_STR:    return 'STR'
    if rvol_ok and rsm_ok:   return 'Prime'
    if rvol_ok:              return 'RVOL'
    if rsm_ok:               return 'RSM'
    return 'SMA50'


def _criteria_label_intraday(sig: dict) -> str:
    return sig.get('criteria', 'SMA50')


def _kind_label(kind, angle=None) -> str:
    if str(kind or '').lower() == 'tl':
        return f'TL ({float(angle):.0f}°)' if angle is not None else 'TL'
    return 'Hz'


def _crit_color(crit: str) -> str:
    return {'Prime': '#5865F2', 'RVOL': '#00b900', 'RSM': '#e67700',
            'STR': '#e03131'}.get(crit, '#888888')


# ── Intraday alert builders ───────────────────────────────────────────────────

def _build_signal_bubble(sig: dict, cfg: dict, time_str: str) -> dict:
    """One Flex bubble per intraday breakout signal."""
    ticker  = sig.get('ticker', '').replace('.BK', '')
    close_v = float(sig.get('close', 0) or 0)
    level_v = float(sig.get('level', close_v) or close_v)
    kind    = _kind_label(sig.get('kind'), sig.get('tl_angle'))
    crit    = _criteria_label_intraday(sig)
    chg_pct = (close_v - level_v) / level_v * 100 if level_v > 0 else 0
    chg_str = f'{chg_pct:+.1f}%'
    chg_col = '#00b900' if chg_pct >= 0 else '#e03131'
    crit_col = _crit_color(crit)

    body = [
        {'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
            _ltext(ticker, color='#1a1a1a', size='xl', weight='bold'),
            _ltext(chg_str, color=chg_col, size='sm', weight='bold', align='end'),
        ]},
        _lrow('Level', f'฿{level_v:.2f}'),
        _lrow('Price', f'฿{close_v:.2f}'),
        _lrow('Type',  kind),
        {'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': [
            _ltext('Criteria', color='#888888', size='sm', flex=3),
            _ltext(crit, color=crit_col, size='sm', weight='bold', flex=4, align='end'),
        ]},
    ]

    return {
        'type': 'flex',
        'altText': f'▲ {ticker} breakout {chg_str} · {crit}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader('▲ Live breakout', f'{time_str} BKK · Intraday', '#5865F2'),
            'body':   {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                       'paddingAll': '12px', 'contents': body},
            'footer': _lbtn('View dashboard', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_intraday_summary_bubble(signals: list, time_str: str) -> dict:
    """Single summary bubble listing all intraday signals (for 5+ stocks)."""
    sort_order = {'Prime': 0, 'RVOL': 1, 'RSM': 2, 'STR': 3, 'SMA50': 4}
    sorted_sigs = sorted(
        signals,
        key=lambda s: (sort_order.get(_criteria_label_intraday(s), 9), s.get('ticker', '')),
    )
    rows = []
    for s in sorted_sigs:
        ticker   = s.get('ticker', '').replace('.BK', '')
        close_v  = float(s.get('close', 0) or 0)
        level_v  = float(s.get('level', close_v) or close_v)
        crit     = _criteria_label_intraday(s)
        chg_pct  = (close_v - level_v) / level_v * 100 if level_v > 0 else 0
        chg_str  = f'{chg_pct:+.1f}%'
        chg_col  = '#00b900' if chg_pct >= 0 else '#e03131'
        rows.append({
            'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': [
                _ltext(ticker, color='#1a1a1a', size='xs', weight='bold', flex=3),
                _ltext(f'฿{level_v:.2f}', color='#888888', size='xs', flex=3),
                _ltext(chg_str, color=chg_col, size='xs', weight='bold', flex=2, align='end'),
                _ltext(crit, color=_crit_color(crit), size='xs', weight='bold',
                       flex=3, align='end'),
            ],
        })

    header_row = {
        'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
            _ltext('TICKER', color='#888888', size='xs', flex=3),
            _ltext('LEVEL',  color='#888888', size='xs', flex=3),
            _ltext('CHG',    color='#888888', size='xs', flex=2, align='end'),
            _ltext('CRIT',   color='#888888', size='xs', flex=3, align='end'),
        ],
    }

    return {
        'type': 'flex',
        'altText': f'▲ {len(signals)} breakout signals · {time_str} BKK',
        'contents': {
            'type': 'bubble', 'size': 'mega',
            'header': _lheader(
                f'▲ {len(signals)} live breakouts', f'{time_str} BKK · Intraday scan', '#5865F2'
            ),
            'body': {
                'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'paddingAll': '12px',
                'contents': [header_row, _lsep()] + rows,
            },
            'footer': _lbtn('View dashboard', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


# ── EOD alert builders ────────────────────────────────────────────────────────

def _build_eod_summary_bubble(signals: list, pending_list: list, date_str: str,
                               cfg: dict) -> dict:
    """Flex bubble with today's breakouts + watchlist count."""
    rvol_min = float(cfg.get('rvol_min', 1.5))
    rsm_min  = float(cfg.get('rs_momentum_min', cfg.get('rsm_min', 70)))
    sort_order = {'Prime': 0, 'RVOL': 1, 'RSM': 2, 'STR': 3, 'SMA50': 4}
    sorted_sigs = sorted(
        signals,
        key=lambda s: (sort_order.get(_criteria_label(s), 9), s.get('ticker', '')),
    )

    rows = []
    for s in sorted_sigs[:12]:  # cap at 12 rows to keep bubble readable
        ticker  = s.get('ticker', '').replace('.BK', '')
        bp      = float(s.get('bp', s.get('close', 0)) or 0)
        close   = float(s.get('close', 0) or 0)
        crit    = _criteria_label(s)
        rvol    = float(s.get('rvol', 0) or 0)
        rsm     = float(s.get('rsm', 0) or 0)
        iv      = '🟢' if rvol >= rvol_min else '🔴'
        ir      = '🟢' if rsm  >= rsm_min  else '🔴'
        rows.append({
            'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': [
                _ltext(ticker,         color='#1a1a1a',         size='xs', weight='bold', flex=3),
                _ltext(f'฿{bp:.2f}',  color='#888888',         size='xs',               flex=3),
                _ltext(crit,           color=_crit_color(crit), size='xs', weight='bold', flex=3),
                _ltext(f'{iv}{ir}',    color='#222222',         size='xs',               flex=2,
                       align='end'),
            ],
        })

    if len(signals) > 12:
        rows.append(_ltext(f'… and {len(signals) - 12} more', color='#888888', size='xs'))

    header_row = {
        'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
            _ltext('TICKER', color='#888888', size='xs', flex=3),
            _ltext('LEVEL',  color='#888888', size='xs', flex=3),
            _ltext('CRIT',   color='#888888', size='xs', flex=3),
            _ltext('RVOL/RSM', color='#888888', size='xs', flex=2, align='end'),
        ],
    }

    footer_text = f'{len(pending_list)} stocks on watchlist for tomorrow'

    return {
        'type': 'flex',
        'altText': f'◑ EOD scan {date_str} · {len(signals)} breakouts',
        'contents': {
            'type': 'bubble', 'size': 'mega',
            'header': _lheader(
                f'◑ EOD scan · {len(signals)} breakouts',
                f'{date_str} · {footer_text}',
                '#3BA55C',
            ),
            'body': {
                'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'paddingAll': '12px',
                'contents': [header_row, _lsep()] + rows,
            },
            'footer': _lbtn('View chart', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


# ── Review / fakeout builders ─────────────────────────────────────────────────

def _build_fakeout_bubble(signals: list, time_str: str) -> dict:
    """Bubble listing fakeout / false-breakout warnings."""
    rows = []
    for s in signals:
        ticker  = s.get('ticker', '').replace('.BK', '')
        kind    = _kind_label(s.get('kind'), s.get('tl_angle'))
        level   = float(s.get('level', 0) or 0)
        close   = float(s.get('close', 0) or 0)
        gap_pct = (close - level) / level * 100 if level > 0 else 0
        gap_str = f'{gap_pct:+.1f}%'
        rows.append({
            'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': [
                _ltext(ticker, color='#1a1a1a', size='xs', weight='bold', flex=3),
                _ltext(kind,   color='#888888', size='xs',                flex=3),
                _ltext(f'฿{level:.2f}', color='#888888', size='xs',      flex=3),
                _ltext(gap_str, color='#e03131', size='xs', weight='bold',
                       flex=2, align='end'),
            ],
        })

    header_row = {
        'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
            _ltext('TICKER', color='#888888', size='xs', flex=3),
            _ltext('TYPE',   color='#888888', size='xs', flex=3),
            _ltext('LEVEL',  color='#888888', size='xs', flex=3),
            _ltext('GAP',    color='#888888', size='xs', flex=2, align='end'),
        ],
    }

    return {
        'type': 'flex',
        'altText': f'▼ {len(signals)} fakeout warning(s) · {time_str} BKK',
        'contents': {
            'type': 'bubble', 'size': 'mega',
            'header': _lheader(
                f'▼ Fakeout warning · {len(signals)} stocks',
                f'{time_str} BKK · Exit or tighten stop',
                '#e03131',
            ),
            'body': {
                'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'paddingAll': '12px',
                'contents': [header_row, _lsep()] + rows + [
                    _lsep(),
                    _ltext('⚡ Market closes 16:30 BKK', color='#e03131', size='xs'),
                ],
            },
            'footer': _lbtn('View dashboard', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


# ── Paper-trade Flex bubbles (kept from output/notifications.py) ──────────────

def _build_trade_open_bubble(event: dict, cfg: dict) -> dict:
    rvol_min = float(cfg.get('rvol_min', 1.5))
    rsm_min  = float(cfg.get('rs_momentum_min', cfg.get('rsm_min', 70)))
    ticker   = event.get('ticker', '')
    entry    = float(event.get('price', 0))
    level    = float(event.get('entry_level', entry))
    shares   = int(event.get('shares', 0))
    value    = shares * entry
    crit     = event.get('criteria', '—')
    kind     = _kind_label(event.get('kind'))
    rvol     = float(event.get('rvol', 0) or 0)
    rsm      = float(event.get('rsm', 0) or 0)
    stretch  = float(event.get('stretch', 0) or 0)
    chg_pct  = (entry - level) / level * 100 if level > 0 else 0
    chg_str  = f'{chg_pct:+.1f}%'
    chg_col  = '#00b900' if chg_pct >= 0 else '#e03131'
    stamp    = str(event.get('at', ''))[:16].replace('T', ' ')

    return {
        'type': 'flex',
        'altText': f'Trade opened: {ticker}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader('▶ Trade opened', f'{stamp} · Simulated', '#5865F2'),
            'body': {
                'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'paddingAll': '12px',
                'contents': [
                    {'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
                        _ltext(ticker, color='#1a1a1a', size='xl', weight='bold'),
                        _ltext(chg_str, color=chg_col, size='sm', weight='bold', align='end'),
                    ]},
                    _lrow('Type',     kind),
                    _lrow('Criteria', crit),
                    _lsep(),
                    _lrow('Entry',  f'฿{entry:.2f}'),
                    _lrow('Shares', f'{shares:,}'),
                    _lrow('Value',  f'฿{value:,.0f}'),
                    _lsep(),
                    _lrow('RVol', f'{rvol:.1f}×', _metric_color(rvol,    rvol_min)),
                    _lrow('RSM',  f'{rsm:.0f}',   _metric_color(rsm,     rsm_min)),
                    _lrow('STR',  f'{stretch:.1f}x', _metric_color(stretch, MAX_STR, invert=True)),
                ],
            },
            'footer': _lbtn('View chart', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_trade_close_bubble(event: dict) -> dict:
    ticker       = event.get('ticker', '')
    price        = float(event.get('price', 0))
    shares       = int(event.get('shares', 0))
    shares_rem   = event.get('shares_remaining')
    pnl          = float(event.get('pnl', 0))
    running_pnl  = event.get('running_pnl')
    ret_pct      = float(event.get('ret_pct', 0))
    reason       = str(event.get('reason', 'SELL'))
    stamp        = str(event.get('at', ''))[:16].replace('T', ' ')
    next_tp      = event.get('next_tp')
    sl           = event.get('sl')
    is_profit    = pnl >= 0
    is_partial   = reason in ('TP1', 'TP2')

    title_map = {
        'TP1': 'TP1 hit — 30% exit', 'TP2': 'TP2 hit — partial exit',
        'EMA10': 'Trade closed — trail stop', 'FALSE_BREAKOUT': 'False breakout — closed',
        'SL': 'Stop loss hit', 'BE': 'Breakeven stop hit', 'End': 'End of period — closed',
    }
    title      = title_map.get(reason, f'Trade closed — {reason}')
    header_col = '#e67700' if is_partial else ('#00b900' if is_profit else '#e03131')
    pnl_str    = f'+฿{pnl:,.0f}' if is_profit else f'-฿{abs(pnl):,.0f}'
    pnl_col    = '#00b900' if is_profit else '#e03131'

    body = [
        _ltext(ticker, color='#1a1a1a', size='xl', weight='bold'),
        _lsep(),
        _lrow('Exit price',  f'฿{price:.2f}'),
        _lrow('Shares sold', f'{shares:,}'),
        _lrow('Tranche P&L', f'{pnl_str} ({ret_pct:+.2f}%)', pnl_col),
    ]
    if is_partial and shares_rem is not None:
        body.append(_lsep())
        body.append(_lrow('Shares left', f'{int(shares_rem):,}'))
        if running_pnl is not None:
            rpnl_col = '#00b900' if running_pnl >= 0 else '#e03131'
            rpnl_str = f'+฿{running_pnl:,.0f}' if running_pnl >= 0 else f'-฿{abs(running_pnl):,.0f}'
            body.append(_lrow('Running P&L', rpnl_str, rpnl_col))
        if next_tp:
            body.append(_lrow('Next target', f'฿{next_tp:.2f}'))
        elif sl:
            body.append(_lrow('Trail / SL', f'฿{float(sl):.2f}'))

    return {
        'type': 'flex',
        'altText': f'{title}: {ticker}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader(title, stamp, header_col),
            'body': {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                     'paddingAll': '12px', 'contents': body},
            'footer': _lbtn('View position', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_portfolio_bubble(summary: dict, date_label: str) -> dict:
    capital    = float(summary.get('capital', 0))
    cash       = float(summary.get('cash', 0))
    realized   = float(summary.get('realized_pnl', 0))
    open_count = int(summary.get('open_count', 0))
    closed_count = int(summary.get('closed_count', 0))
    equity     = cash + realized
    ret_pct    = (equity - capital) / capital * 100 if capital > 0 else 0
    eq_col     = '#00b900' if equity >= capital else '#e03131'

    body = [
        {'type': 'box', 'layout': 'vertical', 'margin': 'none', 'contents': [
            _ltext('Total equity',       color='#888888',  size='xs'),
            _ltext(f'฿{equity:,.0f}',   color=eq_col,     size='xxl', weight='bold'),
            _ltext(f'{ret_pct:+.1f}% total return', color=eq_col, size='xs'),
        ]},
        _lsep(),
        _lrow('Cash',         f'฿{cash:,.0f}'),
        _lrow('Open trades',  str(open_count)),
        _lrow('Closed',       str(closed_count)),
        _lrow('Realized P&L', f'{"+"if realized>=0 else ""}฿{abs(realized):,.0f}',
              '#00b900' if realized >= 0 else '#e03131'),
    ]

    recent = summary.get('recent_closed', [])
    if recent:
        body.append(_lsep())
        body.append(_ltext('Recent closes', color='#888888', size='xs', weight='bold'))
        for t in recent[:4]:
            pnl   = float(t.get('pnl', 0) or 0)
            col   = '#00b900' if pnl >= 0 else '#e03131'
            label = f"{t.get('ticker','?')} · {t.get('reason','—')}"
            val   = f"{'+'if pnl>=0 else ''}฿{abs(pnl):,.0f}"
            body.append(_lrow(label, val, col))

    return {
        'type': 'flex',
        'altText': f'Portfolio snapshot · {date_label}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader('◑ Portfolio snapshot', date_label, '#e67700'),
            'body': {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                     'paddingAll': '12px', 'contents': body},
            'footer': _lbtn('View dashboard', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_history_bubble(closed_trades: list) -> dict:
    wins   = [t for t in closed_trades if float(t.get('pnl', 0)) > 0]
    losses = [t for t in closed_trades if float(t.get('pnl', 0)) <= 0]
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    avg_win  = sum(float(t.get('pnl', 0)) for t in wins)   / len(wins)   if wins   else 0
    avg_loss = sum(float(t.get('pnl', 0)) for t in losses) / len(losses) if losses else 0

    rows = []
    for t in closed_trades:
        pnl    = float(t.get('pnl', 0))
        col    = '#00b900' if pnl >= 0 else '#e03131'
        reason = str(t.get('close_reason') or t.get('reason') or '—')[:6]
        rows.append({
            'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': [
                _ltext(t.get('ticker', '?'), color='#1a1a1a', size='xs', weight='bold', flex=3),
                _ltext('Win' if pnl > 0 else 'Loss', color=col, size='xs', flex=2),
                _ltext(reason, color='#888888', size='xs', flex=3),
                _ltext(f'{"+"if pnl>=0 else ""}฿{abs(pnl):,.0f}', color=col, size='xs',
                       weight='bold', flex=4, align='end'),
            ],
        })

    header_row = {
        'type': 'box', 'layout': 'horizontal', 'margin': 'none', 'contents': [
            _ltext('TICKER', color='#888888', size='xs', flex=3),
            _ltext('RESULT', color='#888888', size='xs', flex=2),
            _ltext('REASON', color='#888888', size='xs', flex=3),
            _ltext('P&L',    color='#888888', size='xs', flex=4, align='end'),
        ],
    }

    return {
        'type': 'flex',
        'altText': f'Trade history — last {len(closed_trades)} trades',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader(f'Trade history — last {len(closed_trades)}',
                               'Closed positions', '#555555'),
            'body': {
                'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'paddingAll': '12px',
                'contents': [header_row, {'type': 'separator', 'margin': 'xs'}] + rows + [
                    _lsep(),
                    _lrow('Win rate', f'{win_rate:.0f}%  ({len(wins)}/{len(closed_trades)})',
                          '#00b900' if win_rate >= 50 else '#e03131'),
                    _lrow('Avg win',  f'+฿{avg_win:,.0f}',      '#00b900'),
                    _lrow('Avg loss', f'-฿{abs(avg_loss):,.0f}', '#e03131'),
                ],
            },
            'footer': _lbtn('View dashboard', f'{APP_BASE_URL}/'),
            'styles': {'footer': {'separator': True}},
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────

def send_intraday_alert(signals: list, now: datetime, cfg: dict) -> bool:
    """LINE — live breakout signals. Individual bubbles for ≤4 stocks, summary for more."""
    if not signals:
        return False
    time_str = now.strftime('%H:%M')

    if len(signals) <= 4:
        messages = [_build_signal_bubble(s, cfg, time_str) for s in signals]
    else:
        messages = [_build_intraday_summary_bubble(signals, time_str)]

    ok = _send(f'INTRADAY {time_str}', messages)
    logger.info('LINE intraday alert %s — %d signals', 'sent' if ok else 'failed', len(signals))
    return ok


def send_review_alert(signals: list, now: datetime, cfg: dict) -> bool:
    """LINE — fakeout warning bubble."""
    if not signals:
        return False
    time_str = now.strftime('%H:%M')
    ok = _send(f'FAKEOUT {time_str}', [_build_fakeout_bubble(signals, time_str)])
    logger.info('LINE fakeout alert %s — %d fakeouts', 'sent' if ok else 'failed', len(signals))
    return ok


def send_eod_alert(today_signals: list, pending_list: list, results: list,
                   date_str: str, cfg: dict, **_kwargs) -> bool:
    """LINE — EOD breakout summary + watchlist count."""
    date_fmt = date_str.replace('_', '-')
    if not today_signals:
        msg = {
            'type': 'flex',
            'altText': f'◑ EOD scan {date_fmt} — no breakouts',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'header': _lheader('◑ EOD scan', f'{date_fmt} · No breakouts today', '#3BA55C'),
                'body': {
                    'type': 'box', 'layout': 'vertical', 'paddingAll': '12px',
                    'contents': [
                        _ltext(f'{len(pending_list)} stocks on watchlist for tomorrow.',
                               color='#888888', size='sm'),
                    ],
                },
                'footer': _lbtn('View chart', f'{APP_BASE_URL}/'),
                'styles': {'footer': {'separator': True}},
            },
        }
        ok = _send(f'EOD {date_fmt}', [msg])
    else:
        bubble = _build_eod_summary_bubble(today_signals, pending_list, date_fmt, cfg)
        ok = _send(f'EOD {date_fmt}', [bubble])

    logger.info('LINE EOD alert %s — %d breakouts', 'sent' if ok else 'failed',
                len(today_signals))
    return ok


def send_trade_update(events: list, now: datetime, cfg: dict | None = None) -> bool:
    """LINE — Flex bubble per BUY/SELL paper trade event."""
    if not events:
        return False
    _cfg = cfg or TRADE_CFG
    messages = []
    for event in events:
        action = event.get('action', '')
        if action == 'BUY':
            messages.append(_build_trade_open_bubble(event, _cfg))
        elif action == 'SELL':
            messages.append(_build_trade_close_bubble(event))
    if not messages:
        return False
    ok = _send('PAPER TRADE UPDATE', messages)
    logger.info('LINE trade update %s — %d events', 'sent' if ok else 'failed', len(messages))
    return ok


def send_portfolio_summary(summary: dict, date_label: str) -> bool:
    """LINE — portfolio snapshot bubble."""
    if not summary:
        return False
    ok = _send(f'PORTFOLIO {date_label}', [_build_portfolio_bubble(summary, date_label)])
    logger.info('LINE portfolio summary %s', 'sent' if ok else 'failed')
    return ok


def send_trade_history(closed_trades: list, n: int = 10) -> bool:
    """LINE — trade history table, last N closed trades."""
    recent = closed_trades[-n:] if len(closed_trades) > n else closed_trades
    if not recent:
        return False
    ok = _send('TRADE HISTORY', [_build_history_bubble(recent)])
    logger.info('LINE trade history %s — %d trades', 'sent' if ok else 'failed', len(recent))
    return ok
