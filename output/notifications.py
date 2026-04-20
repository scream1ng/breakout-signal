"""
notifications.py — Centralized notification logic for Discord and LINE.
"""

import os
import time
import json
from datetime import datetime

import requests


DISCORD_LIMIT = 1800
LINE_LIMIT = 4800
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
OUTBOX_LOG_PATH = os.path.join(DATA_DIR, 'notification_outbox.jsonl')
MESSAGE_LIMIT = 1900
_ANSI = {
    'Prime': '\033[1;35m',
    'STR': '\033[1;31m',
    'RVOL': '\033[1;34m',
    'RSM': '\033[1;32m',
    'SMA50': '\033[1;33m',
    'RESET': '\033[0m',
}


def get_chart_url():
    base_url = os.environ.get('APP_BASE_URL', '').strip().rstrip('/')
    if base_url:
        return f'{base_url}/'

    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
    if domain:
        return f'https://{domain}/'

    return 'https://breakout-signal.up.railway.app/'


def _load_env():
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
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
    discord_url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    line_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
    line_mode = os.environ.get('LINE_MODE', 'push').strip().lower() or 'push'

    raw_targets = os.environ.get('LINE_TO', '').strip()
    line_targets = [value.strip() for value in raw_targets.split(',') if value.strip()]
    for fallback in ('LINE_USER_ID', 'LINE_GROUP_ID', 'LINE_ROOM_ID'):
        value = os.environ.get(fallback, '').strip()
        if value and value not in line_targets:
            line_targets.append(value)

    return discord_url, line_token, line_targets, line_mode


def _post_discord(url: str, text: str) -> bool:
    try:
        response = requests.post(url, json={'content': text}, timeout=10)
        if response.status_code not in (200, 204):
            print(f'  Discord notification error: {response.status_code} {response.text[:120]}')
            return False
        return True
    except Exception as exc:
        print(f'  Discord notification error: {exc}')
        return False


def _push_line(token: str, target: str, text: str) -> bool:
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    payload = {
        'to': target,
        'messages': [{'type': 'text', 'text': text}],
    }
    try:
        response = requests.post(
            'https://api.line.me/v2/bot/message/push',
            headers=headers,
            json=payload,
            timeout=10,
        )
        if response.status_code != 200:
            print(f'  LINE notification error: {response.status_code} {response.text[:120]}')
            return False
        return True
    except Exception as exc:
        print(f'  LINE notification error: {exc}')
        return False


def _broadcast_line(token: str, text: str) -> bool:
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    payload = {
        'messages': [{'type': 'text', 'text': text}],
    }
    try:
        response = requests.post(
            'https://api.line.me/v2/bot/message/broadcast',
            headers=headers,
            json=payload,
            timeout=10,
        )
        if response.status_code != 200:
            print(f'  LINE broadcast error: {response.status_code} {response.text[:120]}')
            return False
        return True
    except Exception as exc:
        print(f'  LINE broadcast error: {exc}')
        return False


def _log_message(channel: str, target: str, header: str, message: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    entry = dict(
        at=datetime.utcnow().isoformat(timespec='seconds'),
        channel=channel,
        target=target,
        header=header,
        message=message,
    )
    with open(OUTBOX_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def _join_blocks(parts: list[str]) -> str:
    return '\n\n'.join([part for part in parts if part])


def _chunk_message(header: str, entries: list[str], footer: str | None, limit: int) -> list[str]:
    entries = entries or ['No items.']
    messages = []
    current = []
    chunk_header = header.strip() if header else ''

    for entry in entries:
        candidate = []
        if chunk_header:
            candidate.append(chunk_header)
        candidate.extend(current + [entry])
        if len(_join_blocks(candidate)) > limit and current:
            messages.append(_join_blocks(([chunk_header] if chunk_header else []) + current))
            chunk_header = ''
            current = [entry]
        else:
            current.append(entry)

    tail = []
    if chunk_header:
        tail.append(chunk_header)
    tail.extend(current)
    if footer:
        candidate = tail + [footer]
        if len(_join_blocks(candidate)) > limit and tail:
            messages.append(_join_blocks(tail))
            tail = [footer]
        else:
            tail.append(footer)
    if tail:
        messages.append(_join_blocks(tail))
    return messages


def _send_line_messages(header: str, messages: list[str]) -> bool:
    discord_url, line_token, line_targets, line_mode = _notification_targets()
    if not line_token:
        return False

    ok = True
    if line_mode == 'broadcast':
        for message in messages:
            _log_message('line', 'broadcast', header, message)
            if not _broadcast_line(line_token, message):
                ok = False
            time.sleep(0.4)
    elif line_targets:
        for target in line_targets:
            for message in messages:
                _log_message('line', target, header, message)
                if not _push_line(line_token, target, message):
                    ok = False
                time.sleep(0.4)

    return ok


def _dispatch_discord_messages(header: str, messages: list[str]) -> bool:
    discord_url, _, _, _ = _notification_targets()
    if not discord_url:
        print('  No notification targets configured — skipping notifications.')
        return False

    ok = True
    for message in messages:
        _log_message('discord', 'webhook', header, message)
        if not _post_discord(discord_url, message):
            ok = False
        time.sleep(0.4)
    return ok


def _dispatch(header: str, entries: list[str], footer: str | None = None, enable_discord: bool = True, enable_line: bool = True) -> bool:
    discord_url, line_token, line_targets, line_mode = _notification_targets()
    if (enable_discord and not discord_url) and (enable_line and not line_token):
        print('  No notification targets configured — skipping notifications.')
        return False

    ok = True

    if enable_discord and discord_url:
        for message in _chunk_message(header, entries, footer, DISCORD_LIMIT):
            _log_message('discord', 'webhook', header, message)
            if not _post_discord(discord_url, message):
                ok = False
            time.sleep(0.4)

    if enable_line and line_token:
        line_messages = _chunk_message(header, entries, footer, LINE_LIMIT)
        if line_mode == 'broadcast':
            for message in line_messages:
                _log_message('line', 'broadcast', header, message)
                if not _broadcast_line(line_token, message):
                    ok = False
                time.sleep(0.4)
        elif line_targets:
            for target in line_targets:
                for message in line_messages:
                    _log_message('line', target, header, message)
                    if not _push_line(line_token, target, message):
                        ok = False
                    time.sleep(0.4)

    return ok


def _criteria_label(sig: dict) -> str:
    stretch = sig.get('stretch', 0)
    rvol_ok = sig.get('rvol_ok', False)
    rsm_ok = sig.get('rsm_ok', False)
    if stretch > 4:
        return 'STR'
    if rvol_ok and rsm_ok:
        return 'Prime'
    if rvol_ok:
        return 'RVOL'
    if rsm_ok:
        return 'RSM'
    return 'SMA50'


def _criteria_sort_key(sig: dict) -> int:
    return {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}.get(_criteria_label(sig), 9)


def _kind_label(kind, angle=None) -> str:
    kind_norm = str(kind or '').lower()
    if kind_norm == 'tl':
        return f'TL {float(angle):.0f}deg' if angle is not None else 'TL'
    return 'Hz'


def _fmt_price(value) -> str:
    if value is None:
        return '-'
    try:
        return f'{float(value):.2f}'
    except Exception:
        return str(value)


def _fmt_multiple(value) -> str:
    try:
        return f'{float(value):.1f}x'
    except Exception:
        return '-'


def _checkmark(ok: bool) -> str:
    green = '\033[1;32m'
    red = '\033[1;31m'
    reset = '\033[0m'
    return f'{green}✓{reset}' if ok else f'{red}✗{reset}'


def _make_ansi_block(header_row: str, divider: str, rows: list[str]) -> str:
    return f"```ansi\n{header_row}\n{divider}\n" + "\n".join(rows) + f"\n{_ANSI['RESET']}```"


def _chunk_ansi_rows(rows: list[str], header_row: str, divider: str, prefix: str = '', suffix: str = '') -> list[str]:
    rows = rows or ['No breakout signals today.']
    chunks = []
    current_rows = []

    for row in rows:
        test = _make_ansi_block(header_row, divider, current_rows + [row])
        if len(test) > MESSAGE_LIMIT and current_rows:
            while current_rows and current_rows[-1] == '':
                current_rows.pop()
            chunks.append(_make_ansi_block(header_row, divider, current_rows))
            current_rows = [row] if row else []
        else:
            current_rows.append(row)

    while current_rows and current_rows[-1] == '':
        current_rows.pop()
    if current_rows:
        chunks.append(_make_ansi_block(header_row, divider, current_rows))

    if chunks and prefix:
        chunks[0] = f'{prefix}\n{chunks[0]}'
    if chunks and suffix:
        chunks[-1] = f'{chunks[-1]}\n{suffix}'
    return chunks


def _eod_entry(sig: dict) -> str:
    ticker = sig['ticker'].replace('.BK', '').replace('.AX', '')
    crit = _criteria_label(sig)
    return (
        f'{ticker} | {_kind_label(sig.get("kind"), sig.get("tl_angle"))} | {crit}\n'
        f'Level {_fmt_price(sig.get("bp"))} -> Close {_fmt_price(sig.get("close"))}\n'
        f'RVol {_fmt_multiple(sig.get("rvol"))} | RSM {sig.get("rsm", 0):.0f} | STR {_fmt_multiple(sig.get("stretch"))}'
    )


def _intraday_entry(sig: dict) -> str:
    ticker = sig['ticker'].replace('.BK', '').replace('.AX', '')
    return (
        f'{ticker} | {_kind_label(sig.get("kind"), sig.get("tl_angle"))} | {sig.get("criteria", "-")}\n'
        f'Close {_fmt_price(sig.get("close"))} above {_fmt_price(sig.get("level"))}\n'
        f'ProjRVol {_fmt_multiple(sig.get("proj_rvol"))} | RSM {sig.get("rsm", 0):.0f} | STR {_fmt_multiple(sig.get("stretch"))}'
    )


def _review_entry(sig: dict) -> str:
    ticker = sig['ticker'].replace('.BK', '').replace('.AX', '')
    return (
        f'{ticker} | {_kind_label(sig.get("kind"), sig.get("tl_angle"))} | {sig.get("criteria", "-")}\n'
        f'Close {_fmt_price(sig.get("close"))} below {_fmt_price(sig.get("level"))}\n'
        f'RVol {_fmt_multiple(sig.get("cur_rvol"))} | RSM {sig.get("rsm", 0):.0f} | STR {_fmt_multiple(sig.get("stretch"))}'
    )


def _recap_entry(item: dict) -> str:
    return (
        f'{item.get("ticker", "-")} | {item.get("status", "-")}\n'
        f'Level {_fmt_price(item.get("level"))} | Alert {item.get("alerted_at", "-")}\n'
        f'{item.get("note", "")}'.strip()
    ).strip()


def send_eod_alert(today_signals, pending_list, results, date_str, cfg, intraday_recap=None):
    date_fmt = date_str.replace('_', '-')
    header = f'END OF DAY SCAN | {date_fmt}'
    count_line = f'`{len(pending_list)} watchlist  ·  {len(today_signals)} breakout{'s' if len(today_signals) != 1 else ''}`'
    header_row = f"{'Ticker':<8}  {'T':<10}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'RVol':>9}  {'RSM':>7}  {'STR':>8}"
    divider = '─' * len(header_row)
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min = cfg.get('rs_momentum_min', cfg.get('rsm_min', 70))

    rows = []
    last_crit = None
    for sig in sorted(today_signals, key=lambda item: (_criteria_sort_key(item), item['ticker'])):
        ticker = sig['ticker'].replace('.BK', '').replace('.AX', '')
        crit = _criteria_label(sig)
        stretch = sig.get('stretch', 0)
        rvol = sig.get('rvol', 0)
        rsm = sig.get('rsm', 0)
        str_disp = f'{stretch:.1f}x' if stretch else '—'
        color = _ANSI.get(crit, '')
        reset = _ANSI['RESET']
        if last_crit is not None and crit != last_crit:
            rows.append('')
        last_crit = crit
        angle = sig.get('tl_angle')
        kind_label = f'TL ({angle:.0f}°)' if str(sig.get('kind')).lower() == 'tl' and angle is not None else ('TL' if str(sig.get('kind')).lower() == 'tl' else 'Hz')
        rvol_str = f'{rvol:>5.1f}x{_checkmark(rvol >= rvol_min)}'
        rsm_str = f'{rsm:>4.0f}{_checkmark(rsm >= rsm_min)}'
        str_str = f'{str_disp:>5}{_checkmark(stretch <= 4)}'
        rows.append(
            f"{color}{ticker:<8}{reset}  {kind_label:<10}  {color}{crit:<6}{reset}  "
            f"{sig.get('bp', 0):>8.2f}  {sig.get('close', 0):>8.2f}  {rvol_str}  {rsm_str}  {str_str}"
        )

    messages = _chunk_ansi_rows(
        rows,
        header_row,
        divider,
        prefix=f'**{header}**\n{count_line}',
        suffix=f'**View charts:** {get_chart_url()}',
    )
    ok = _dispatch_discord_messages(header, messages)
    print(f'  {"Notification sent" if ok else "Notification failed"} — {len(today_signals)} breakouts')


def send_intraday_alert(signals, now, cfg):
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')
    header = f'INTRADAY SCAN | {date_str} {time_str} BKK'
    count_line = f'`{len(signals)} signal{'s' if len(signals) != 1 else ''}`'
    header_row = f"{'Ticker':<8}  {'T':<10}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'ProjRVol':>10}  {'RSM':>7}  {'STR':>8}"
    divider = '─' * len(header_row)
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min = cfg.get('rs_momentum_min', cfg.get('rsm_min', 70))
    sort_key = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}

    rows = []
    last_crit = None
    for sig in sorted(signals, key=lambda item: (sort_key.get(item['criteria'], 9), item['ticker'])):
        crit = sig['criteria']
        color = _ANSI.get(crit, '')
        reset = _ANSI['RESET']
        stretch = sig.get('stretch', 0)
        proj_rvol = sig.get('proj_rvol', 0)
        rsm = sig.get('rsm', 0)
        str_disp = f'{stretch:.1f}x' if stretch else '—'
        if last_crit is not None and crit != last_crit:
            rows.append('')
        last_crit = crit
        angle = sig.get('tl_angle')
        kind_label = f'TL ({angle:.0f}°)' if str(sig.get('kind')).lower() == 'tl' and angle is not None else ('TL' if str(sig.get('kind')).lower() == 'tl' else 'Hz')
        proj_str = f'{proj_rvol:>8.1f}x{_checkmark(proj_rvol >= rvol_min)}'
        rsm_str = f'{rsm:>4.0f}{_checkmark(rsm >= rsm_min)}'
        str_str = f'{str_disp:>5}{_checkmark(stretch <= 4)}'
        rows.append(
            f"{color}{sig['ticker']:<8}{reset}  {kind_label:<10}  {color}{crit:<6}{reset}  "
            f"{sig['level']:>8.2f}  {sig['close']:>8.2f}  {proj_str}  {rsm_str}  {str_str}"
        )

    messages = _chunk_ansi_rows(rows, header_row, divider, prefix=f'**⚡ {header}**\n{count_line}')
    ok = _dispatch_discord_messages(header, messages)
    print(f'  {"Notification sent" if ok else "Notification failed"} — {len(signals)} signals')


def send_review_alert(signals, now, cfg):
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')
    header = f'FALSE BREAKOUTS | {date_str} {time_str} BKK'
    count_line = f'`{len(signals)} false signal{'s' if len(signals) != 1 else ''} fallen below pivot`'
    header_row = f"{'Ticker':<8}  {'T':<10}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'RVol':>9}  {'RSM':>7}  {'STR':>8}"
    divider = '─' * len(header_row)
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min = cfg.get('rs_momentum_min', cfg.get('rsm_min', 70))

    rows = []
    reset = _ANSI['RESET']
    for sig in sorted(signals, key=lambda item: item['ticker']):
        crit = sig.get('criteria', '')
        color = _ANSI.get(crit, '')
        stretch = sig.get('stretch', 0)
        rvol = sig.get('cur_rvol', 0)
        rsm = sig.get('rsm', 0)
        str_disp = f'{stretch:.1f}x' if stretch else '—'
        angle = sig.get('tl_angle')
        kind_label = f'TL ({angle:.0f}°)' if str(sig.get('kind')).lower() == 'tl' and angle is not None else ('TL' if str(sig.get('kind')).lower() == 'tl' else 'Hz')
        rvol_str = f'{rvol:>5.1f}x{_checkmark(rvol >= rvol_min)}'
        rsm_str = f'{rsm:>4.0f}{_checkmark(rsm >= rsm_min)}'
        str_str = f'{str_disp:>5}{_checkmark(stretch <= 4)}'
        rows.append(
            f"\033[1;31m{sig['ticker']:<8}{reset}  {kind_label:<10}  {color}{crit:<6}{reset}  "
            f"{sig['level']:>8.2f}  {sig['close']:>8.2f}{_checkmark(sig['close'] >= sig['level'])} "
            f"{rvol_str}  {rsm_str}  {str_str}"
        )

    messages = _chunk_ansi_rows(rows, header_row, divider, prefix=f'**⚠️ {header}**\n{count_line}')
    ok = _dispatch_discord_messages(header, messages)
    print(f'  {"Notification sent" if ok else "Notification failed"} — {len(signals)} false breakouts')


def send_paper_trade_update(events: list, now, title: str = 'PAPER TRADE UPDATE'):
    if not events:
        return

    line_messages = []
    stamp = now.strftime('%Y-%m-%d %H:%M')
    for event in events:
        if event.get('action') == 'BUY':
            line_messages.append(
                '\n'.join([
                    'PAPER TRADE ENTRY',
                    stamp,
                    '-------------------------',
                    f'BUY {event.get("ticker")} @ {_fmt_price(event.get("price"))} | Qty {event.get("shares", 0)}',
                    f'Cost {event.get("net_value", 0):,.0f} | {event.get("criteria", "-")}',
                    f'Balance {event.get("cash_after", 0):,.0f}',
                ])
            )
        else:
            line_messages.append(
                '\n'.join([
                    'PAPER TRADE EXIT',
                    stamp,
                    '-------------------------',
                    f'SELL {event.get("ticker")} @ {_fmt_price(event.get("price"))} | Qty {event.get("shares", 0)}',
                    f'PnL {event.get("pnl", 0):+,.0f} | Return {event.get("ret_pct", 0):+.2f}%',
                    f'Reason {event.get("reason", "-")}',
                    f'Balance {event.get("cash_after", 0):,.0f}',
                ])
            )

    _send_line_messages(title, line_messages)


def send_paper_trade_summary(summary: dict, date_label: str):
    return
