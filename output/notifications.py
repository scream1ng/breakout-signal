"""
notifications.py — Discord embeds + LINE Flex Messages for SET Breakout Scanner

Discord alerts (send to Discord only):
  send_intraday_alert()  → yellow embed · TICKER/PRICE/CHG/TYPE/CRITERIA table
  send_review_alert()    → red embed    · fakeout cards per stock
  send_eod_alert()       → green embed  · TICKER/PRICE/CHG/TYPE/CRITERIA/RVOL/RSM/STR
                           RVOL/RSM: 🟢 ≥ threshold  🔴 below
                           STR:      🟢 ≤ 4.0         🔴 > 4.0

LINE paper trading (send to LINE only):
  send_paper_trade_update()   → Flex bubble per trade open/close
  send_paper_trade_summary()  → Flex bubble portfolio snapshot
"""

import os
import time
import json
from datetime import datetime

import requests


# ── Constants ─────────────────────────────────────────────────────────────────
ROOT            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR        = os.path.join(ROOT, 'data')
OUTBOX_LOG_PATH = os.path.join(DATA_DIR, 'notification_outbox.jsonl')

DISCORD_COLOR_INTRADAY = 0xFAA61A   # yellow
DISCORD_COLOR_FAKEOUT  = 0xED4245   # red
DISCORD_COLOR_EOD      = 0x3BA55C   # green

MAX_STR = 4.0   # stretch > 4.0 → overextended → red


# ── Environment ───────────────────────────────────────────────────────────────
def _load_env():
    candidates = [
        os.path.join(ROOT, '.env'),
        os.path.join(os.getcwd(), '.env'),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, val = line.partition('=')
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            return


def _notification_targets():
    _load_env()
    discord_url  = os.environ.get('DISCORD_WEBHOOK', '').strip()
    line_token   = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
    line_mode    = os.environ.get('LINE_MODE', 'push').strip().lower() or 'push'
    raw_targets  = os.environ.get('LINE_TO', '').strip()
    line_targets = [v.strip() for v in raw_targets.split(',') if v.strip()]
    for key in ('LINE_USER_ID', 'LINE_GROUP_ID', 'LINE_ROOM_ID'):
        v = os.environ.get(key, '').strip()
        if v and v not in line_targets:
            line_targets.append(v)
    return discord_url, line_token, line_targets, line_mode


def get_chart_url() -> str:
    base = os.environ.get('APP_BASE_URL', '').strip().rstrip('/')
    if base:
        return f'{base}/'
    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
    if domain:
        return f'https://{domain}/'
    return 'https://breakout-signal.up.railway.app/'


# ── Low-level HTTP ────────────────────────────────────────────────────────────
def _post_discord(url: str, payload: dict) -> bool:
    """POST to Discord webhook. payload = {'embeds': [...]} or {'content': ...}"""
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code not in (200, 204):
            print(f'  Discord error: {r.status_code} {r.text[:120]}')
            return False
        return True
    except Exception as e:
        print(f'  Discord error: {e}')
        return False


def _push_line(token: str, target: str, messages: list) -> bool:
    """POST list of LINE message dicts (text or flex) to a single target."""
    try:
        r = requests.post(
            'https://api.line.me/v2/bot/message/push',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'to': target, 'messages': messages},
            timeout=10,
        )
        if r.status_code != 200:
            print(f'  LINE push error: {r.status_code} {r.text[:120]}')
            return False
        return True
    except Exception as e:
        print(f'  LINE push error: {e}')
        return False


def _broadcast_line(token: str, messages: list) -> bool:
    """Broadcast list of LINE message dicts to all followers."""
    try:
        r = requests.post(
            'https://api.line.me/v2/bot/message/broadcast',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'messages': messages},
            timeout=10,
        )
        if r.status_code != 200:
            print(f'  LINE broadcast error: {r.status_code} {r.text[:120]}')
            return False
        return True
    except Exception as e:
        print(f'  LINE broadcast error: {e}')
        return False


def _log_message(channel: str, target: str, header: str, payload):
    os.makedirs(DATA_DIR, exist_ok=True)
    entry = dict(
        at=datetime.utcnow().isoformat(timespec='seconds'),
        channel=channel, target=target, header=header,
        message=payload if isinstance(payload, str) else json.dumps(payload),
    )
    with open(OUTBOX_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def _send_discord(header: str, embed: dict) -> bool:
    discord_url, _, _, _ = _notification_targets()
    if not discord_url:
        print('  Discord webhook not configured — skipping.')
        return False
    _log_message('discord', 'webhook', header, embed)
    ok = _post_discord(discord_url, {'embeds': [embed]})
    time.sleep(0.4)
    return ok


def _send_line(header: str, messages: list) -> bool:
    """Send list of LINE message dicts (text/flex) to all configured targets."""
    _, line_token, line_targets, line_mode = _notification_targets()
    if not line_token:
        return False
    ok = True
    if line_mode == 'broadcast':
        _log_message('line', 'broadcast', header, messages)
        if not _broadcast_line(line_token, messages):
            ok = False
        time.sleep(0.4)
    else:
        for target in line_targets:
            _log_message('line', target, header, messages)
            if not _push_line(line_token, target, messages):
                ok = False
            time.sleep(0.4)
    return ok


# ── Color + format helpers ────────────────────────────────────────────────────
def _criteria_label(sig: dict) -> str:
    stretch = float(sig.get('stretch', 0) or 0)
    rvol_ok = bool(sig.get('rvol_ok', False))
    rsm_ok  = bool(sig.get('rsm_ok',  False))
    if stretch > MAX_STR:      return 'STR'
    if rvol_ok and rsm_ok:     return 'Prime'
    if rvol_ok:                return 'RVOL'
    if rsm_ok:                 return 'RSM'
    return 'SMA50'


def _criteria_label_intraday(sig: dict) -> str:
    """For intraday signals which use 'criteria' field directly."""
    return sig.get('criteria', 'SMA50')


def _kind_label(kind, angle=None) -> str:
    if str(kind or '').lower() == 'tl':
        return f'TL ({float(angle):.0f}°)' if angle is not None else 'TL'
    return 'Hz'


def _fmt(v, d=2) -> str:
    try:
        return f'{float(v):.{d}f}'
    except Exception:
        return '—'


def _icon_rvol(v, threshold) -> str:
    return '🟢' if float(v or 0) >= threshold else '🔴'


def _icon_rsm(v, threshold) -> str:
    return '🟢' if float(v or 0) >= threshold else '🔴'


def _icon_str(v) -> str:
    """STR ≤ 4.0 = green (acceptable), > 4.0 = red (overextended)."""
    return '🟢' if float(v or 0) <= MAX_STR else '🔴'


# ── Discord embed builders ─────────────────────────────────────────────────────
def _build_intraday_embed(signals: list, time_str: str, cfg: dict) -> dict:
    """Yellow embed with TICKER | PRICE | CHG | TYPE | CRITERIA table."""
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min  = cfg.get('rs_momentum_min', cfg.get('rsm_min', 70))

    sort_order = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}
    sorted_sigs = sorted(signals, key=lambda s: (sort_order.get(_criteria_label_intraday(s), 9), s.get('ticker', '')))

    lines = []
    for s in sorted_sigs:
        ticker   = s.get('ticker', '').replace('.BK', '')
        price    = _fmt(s.get('close'), 2)
        chg      = _fmt(s.get('change_pct', 0), 1) if 'change_pct' in s else '—'
        kind     = _kind_label(s.get('kind'), s.get('tl_angle'))
        crit     = _criteria_label_intraday(s)
        lines.append(f'`{ticker:<8}` `{price:>7}` `{chg:>6}%` `{kind:<10}` **{crit}**')

    header_line = '`TICKER  ` `  PRICE` `   CHG` `TYPE      ` CRITERIA'
    desc = header_line + '\n' + '─' * 52 + '\n' + '\n'.join(lines)

    return {
        'color':  DISCORD_COLOR_INTRADAY,
        'author': {'name': f'▲ Live breakout signals · {len(signals)} stocks · {time_str} BKK'},
        'title':  'Intraday scan — active breakouts',
        'description': desc,
        'footer': {'text': f'Intraday sniper · next scan in 15 min · {get_chart_url()}'},
    }


def _build_fakeout_embed(signals: list, time_str: str) -> dict:
    """Red embed — one block per stock showing pivot / close / gap."""
    blocks = []
    for s in signals:
        ticker  = s.get('ticker', '').replace('.BK', '')
        kind    = _kind_label(s.get('kind'), s.get('tl_angle'))
        pivot   = _fmt(s.get('level'), 2)
        close   = _fmt(s.get('close'), 2)
        gap     = _fmt(float(s.get('close', 0)) - float(s.get('level', 0)), 2)
        chg_pct = (float(s.get('close', 0)) - float(s.get('level', 0))) / float(s.get('level', 1)) * 100
        blocks.append(
            f'**{ticker}** · {kind} fakeout\n'
            f'Pivot `{pivot}` | Close `{close}` ({chg_pct:+.1f}%) | Gap `{gap}`'
        )

    desc = '\n\n'.join(blocks) + '\n\n⚡ Exit or tighten stop — market closes 16:30'

    return {
        'color':  DISCORD_COLOR_FAKEOUT,
        'author': {'name': f'▼ Failed breakout summary · {len(signals)} stocks · {time_str} safety net'},
        'title':  'Fakeout warning — reversed below pivot',
        'description': desc,
        'footer': {'text': f'Safety net check · {time_str} BKK · market closes 16:30'},
    }


def _build_eod_embed(signals: list, cfg: dict, date_str: str) -> dict:
    """Green embed with TICKER|PRICE|CHG|TYPE|CRITERIA|RVOL|RSM|STR table."""
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min  = cfg.get('rs_momentum_min', cfg.get('rsm_min', 70))

    sort_order = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}
    sorted_sigs = sorted(signals, key=lambda s: (sort_order.get(_criteria_label(s), 9), s.get('ticker', '')))

    lines = []
    for s in sorted_sigs:
        ticker   = s.get('ticker', '').replace('.BK', '')
        price    = _fmt(s.get('close'), 2)
        bp       = float(s.get('bp', s.get('close', 0)) or 0)
        close    = float(s.get('close', 0) or 0)
        chg_pct  = (close - bp) / bp * 100 if bp > 0 else 0
        kind     = _kind_label(s.get('kind'), s.get('tl_angle'))
        crit     = _criteria_label(s)
        rvol     = float(s.get('rvol', 0) or 0)
        rsm      = float(s.get('rsm', 0) or 0)
        stretch  = float(s.get('stretch', 0) or 0)

        iv = _icon_rvol(rvol, rvol_min)
        ir = _icon_rsm(rsm, rsm_min)
        is_ = _icon_str(stretch)

        lines.append(
            f'`{ticker:<7}` `{price:>7}` `{chg_pct:>+5.1f}%` '
            f'`{kind:<10}` **{crit:<5}** '
            f'{iv}`{rvol:.1f}×` {ir}`{rsm:.0f}` {is_}`{stretch:.1f}x`'
        )

    header = '`TICKER ` `  PRICE` `  CHG ` `TYPE      ` CRIT  RVOL     RSM   STR'
    desc   = header + '\n' + '─' * 60 + '\n' + '\n'.join(lines)

    return {
        'color':  DISCORD_COLOR_EOD,
        'author': {'name': f'◑ End-of-day watchlist · {len(signals)} active · {date_str}'},
        'title':  'Carry into tomorrow — open positions',
        'description': desc,
        'footer': {'text': f'EOD scanner · 18:05 BKK · {get_chart_url()}'},
    }


# ── LINE Flex Message helpers ─────────────────────────────────────────────────
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


def _lbtn(label: str, url: str, color: str = '#00b900') -> dict:
    return {
        'type': 'box', 'layout': 'vertical', 'paddingAll': '0px',
        'contents': [{
            'type': 'button',
            'action': {'type': 'uri', 'label': label, 'uri': url},
            'color': color, 'style': 'primary', 'height': 'sm',
        }],
    }


def _metric_color(value, threshold, invert=False) -> str:
    """Return green or red hex depending on threshold direction."""
    try:
        passes = float(value) <= threshold if invert else float(value) >= threshold
    except Exception:
        passes = False
    return '#00b900' if passes else '#e03131'


# ── LINE Flex bubble builders ─────────────────────────────────────────────────
def _build_line_trade_open(event: dict, cfg: dict) -> dict:
    """Flex bubble for paper trade BUY event."""
    rvol_min = float(cfg.get('rvol_min', 1.5))
    rsm_min  = float(cfg.get('rs_momentum_min', cfg.get('rsm_min', 70)))

    ticker   = event.get('ticker', '')
    entry    = float(event.get('price', 0))
    level    = float(event.get('entry_level', entry))
    shares   = int(event.get('shares', 0))
    value    = shares * entry
    crit     = event.get('criteria', '—')
    kind     = _kind_label(event.get('kind'), None)
    rvol     = float(event.get('rvol', 0) or 0)
    rsm      = float(event.get('rsm', 0) or 0)
    stretch  = float(event.get('stretch', 0) or 0)
    chg_pct  = (entry - level) / level * 100 if level > 0 else 0
    stamp    = str(event.get('at', ''))[:16].replace('T', ' ')

    chg_str  = f'+{chg_pct:.1f}%' if chg_pct >= 0 else f'{chg_pct:.1f}%'
    chg_col  = '#00b900' if chg_pct >= 0 else '#e03131'

    body_contents = [
        {
            'type': 'box', 'layout': 'horizontal', 'margin': 'none',
            'contents': [
                _ltext(ticker, color='#1a1a1a', size='xl', weight='bold'),
                _ltext(chg_str, color=chg_col, size='sm', weight='bold', align='end'),
            ],
        },
        _lrow('Type',     kind),
        _lrow('Criteria', crit),
        _lsep(),
        _lrow('Entry',    f'฿{entry:.2f}'),
        _lrow('Shares',   f'{shares:,}'),
        _lrow('Value',    f'฿{value:,.0f}'),
        _lsep(),
        _lrow('RVol',  f'{rvol:.1f}×', _metric_color(rvol,    rvol_min)),
        _lrow('RSM',   f'{rsm:.0f}',   _metric_color(rsm,     rsm_min)),
        _lrow('STR',   f'{stretch:.1f}x', _metric_color(stretch, MAX_STR, invert=True)),
    ]

    return {
        'type': 'flex',
        'altText': f'Trade opened: {ticker}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader('▶ Trade opened', f'{stamp} · Simulated', '#5865F2'),
            'body':   {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                       'paddingAll': '12px', 'contents': body_contents},
            'footer': _lbtn('View chart', get_chart_url()),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_line_trade_close(event: dict) -> dict:
    """Flex bubble for paper trade SELL event."""
    ticker      = event.get('ticker', '')
    price       = float(event.get('price', 0))
    shares      = int(event.get('shares', 0))
    pnl         = float(event.get('pnl', 0))
    ret_pct     = float(event.get('ret_pct', 0))
    reason      = str(event.get('reason', 'SELL'))
    stamp       = str(event.get('at', ''))[:16].replace('T', ' ')
    is_profit   = pnl >= 0

    # Title from reason
    title_map = {
        'TP1':            'TP1 hit — 50% exit',
        'TP2':            'TP2 hit — full exit',
        'EMA10':          'Trade closed — trail stop',
        'FALSE_BREAKOUT': 'False breakout — position closed',
        'SL':             'Stop loss hit',
        'BE':             'Breakeven stop hit',
        'End':            'End of period — position closed',
    }
    title       = title_map.get(reason, f'Trade closed — {reason}')
    header_col  = '#00b900' if is_profit else '#e03131'

    pnl_str     = f'+฿{pnl:,.0f}' if is_profit else f'-฿{abs(pnl):,.0f}'
    pnl_col     = '#00b900' if is_profit else '#e03131'
    ret_str     = f'{ret_pct:+.2f}%'

    body_contents = [
        _ltext(ticker, color='#1a1a1a', size='xl', weight='bold'),
        _lsep(),
        _lrow('Sell price',  f'฿{price:.2f}'),
        _lrow('Shares sold', f'{shares:,}'),
        _lrow('Profit',      f'{pnl_str} ({ret_str})', pnl_col),
    ]

    return {
        'type': 'flex',
        'altText': f'{title}: {ticker}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader(title, stamp, header_col),
            'body':   {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                       'paddingAll': '12px', 'contents': body_contents},
            'footer': _lbtn('View position', get_chart_url()),
            'styles': {'footer': {'separator': True}},
        },
    }


def _build_line_portfolio(summary: dict, date_label: str) -> dict:
    """Flex bubble for portfolio snapshot."""
    capital    = float(summary.get('capital', 0))
    cash       = float(summary.get('cash', 0))
    realized   = float(summary.get('realized_pnl', 0))
    open_count = int(summary.get('open_count', 0))
    closed_count = int(summary.get('closed_count', 0))
    equity     = cash + realized  # simplified; actual equity = cash + open position values
    ret_pct    = (equity - capital) / capital * 100 if capital > 0 else 0

    eq_col  = '#00b900' if equity >= capital else '#e03131'
    ret_str = f'{ret_pct:+.1f}%'

    # Recent closed trades
    recent = summary.get('recent_closed', [])
    recent_lines = []
    for t in recent[:4]:
        pnl   = float(t.get('pnl', 0) or 0)
        col   = '#00b900' if pnl >= 0 else '#e03131'
        label = f"{t.get('ticker','?')} · {t.get('reason','—')}"
        val   = f"{'+'if pnl>=0 else ''}฿{abs(pnl):,.0f}"
        recent_lines.append(_lrow(label, val, col))

    body_contents = [
        {
            'type': 'box', 'layout': 'vertical', 'margin': 'none',
            'contents': [
                _ltext('Total equity', color='#888888', size='xs'),
                _ltext(f'฿{equity:,.0f}', color=eq_col, size='xxl', weight='bold'),
                _ltext(f'{ret_str} total return', color=eq_col, size='xs'),
            ],
        },
        _lsep(),
        _lrow('Cash',        f'฿{cash:,.0f}'),
        _lrow('Open trades', str(open_count)),
        _lrow('Closed',      str(closed_count)),
        _lrow('Realized P&L', f'{"+"if realized>=0 else ""}฿{abs(realized):,.0f}',
              '#00b900' if realized >= 0 else '#e03131'),
    ]

    if recent_lines:
        body_contents.append(_lsep())
        body_contents.append(_ltext('Recent closes', color='#888888', size='xs', weight='bold'))
        body_contents.extend(recent_lines)

    return {
        'type': 'flex',
        'altText': f'Portfolio snapshot · {date_label}',
        'contents': {
            'type': 'bubble', 'size': 'kilo',
            'header': _lheader('◑ Portfolio snapshot', date_label, '#e67700'),
            'body':   {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                       'paddingAll': '12px', 'contents': body_contents},
            'footer': _lbtn('View dashboard', get_chart_url()),
            'styles': {'footer': {'separator': True}},
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────
def send_intraday_alert(signals: list, now, cfg: dict) -> bool:
    """Discord only — embed with breakout table. 1 msg per scan, new each time."""
    if not signals:
        return False
    time_str = now.strftime('%H:%M')
    embed = _build_intraday_embed(signals, time_str, cfg)
    ok = _send_discord(f'INTRADAY {time_str}', embed)
    print(f'  {"Discord sent" if ok else "Discord failed"} — {len(signals)} intraday signals')
    return ok


def send_review_alert(signals: list, now, cfg: dict) -> bool:
    """Discord only — fakeout/false-breakout summary embed."""
    if not signals:
        return False
    time_str = now.strftime('%H:%M')
    embed = _build_fakeout_embed(signals, time_str)
    ok = _send_discord(f'FAKEOUT {time_str}', embed)
    print(f'  {"Discord sent" if ok else "Discord failed"} — {len(signals)} fakeouts')
    return ok


def send_eod_alert(today_signals: list, pending_list: list, results: list,
                   date_str: str, cfg: dict, intraday_recap=None) -> bool:
    """Discord only — EOD embed with full metrics table."""
    date_fmt = date_str.replace('_', '-')
    if not today_signals:
        # Send a brief no-signal summary
        embed = {
            'color':  DISCORD_COLOR_EOD,
            'author': {'name': f'◑ End-of-day scan · {date_fmt}'},
            'title':  'No breakouts today',
            'description': f'{len(pending_list)} stocks on watchlist for tomorrow.',
            'footer': {'text': f'EOD scanner · {get_chart_url()}'},
        }
        ok = _send_discord(f'EOD {date_fmt}', embed)
        print(f'  {"Discord sent" if ok else "Discord failed"} — no signals')
        return ok

    embed = _build_eod_embed(today_signals, cfg, date_fmt)
    # Add watchlist count to footer
    embed['footer']['text'] = (
        f'EOD scanner · {len(pending_list)} on watchlist · {get_chart_url()}'
    )
    ok = _send_discord(f'EOD {date_fmt}', embed)
    print(f'  {"Discord sent" if ok else "Discord failed"} — {len(today_signals)} breakouts')
    return ok


def send_paper_trade_update(events: list, now, title: str = 'PAPER TRADE UPDATE') -> bool:
    """LINE only — Flex bubble per BUY or SELL event."""
    if not events:
        return False

    _load_env()
    cfg_rvol = float(os.environ.get('RVOL_MIN', '1.5'))
    cfg_rsm  = float(os.environ.get('RSM_MIN', '70'))
    cfg = {'rvol_min': cfg_rvol, 'rs_momentum_min': cfg_rsm}

    # Try to load config for thresholds
    try:
        import sys
        sys.path.insert(0, ROOT)
        from config import CFG as _CFG
        cfg = _CFG
    except Exception:
        pass

    flex_messages = []
    for event in events:
        action = event.get('action', '')
        if action == 'BUY':
            flex_messages.append(_build_line_trade_open(event, cfg))
        elif action == 'SELL':
            flex_messages.append(_build_line_trade_close(event))

    if not flex_messages:
        return False

    ok = _send_line(title, flex_messages)
    print(f'  {"LINE sent" if ok else "LINE failed"} — {len(flex_messages)} paper trade updates')
    return ok


def send_paper_trade_summary(summary: dict, date_label: str) -> bool:
    """LINE only — portfolio snapshot Flex bubble."""
    if not summary:
        return False
    flex_message = _build_line_portfolio(summary, date_label)
    ok = _send_line(f'PORTFOLIO {date_label}', [flex_message])
    print(f'  {"LINE sent" if ok else "LINE failed"} — portfolio summary')
    return ok
