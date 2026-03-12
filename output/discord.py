"""
discord.py — Send daily scan to Discord webhook.
Reads DISCORD_WEBHOOK from .env or environment.
"""

import os


CHART_URL = "https://scream1ng.github.io/breakout-signal/"


def _load_env():
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
        os.path.join(os.getcwd(), '.env'),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f'  Loading .env from: {path}')
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, val = line.partition('=')
                    key = key.strip(); val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            return
    print('  No .env found.')


def _post(url: str, text: str) -> bool:
    import requests
    try:
        r = requests.post(url, json={'content': text}, timeout=10)
        if r.status_code not in (200, 204):
            print(f'  Discord error: {r.status_code} {r.text[:100]}')
            return False
        return True
    except Exception as e:
        print(f'  Discord error: {e}')
        return False


def _criteria_label(sig: dict) -> str:
    """5-type classification matching chart system."""
    stretch = sig.get('stretch', 0)
    rvol_ok = sig.get('rvol_ok', False)
    rsm_ok  = sig.get('rsm_ok',  False)
    if stretch > 4:        return 'STR'
    if rvol_ok and rsm_ok: return 'Prime'
    if rvol_ok:            return 'RVOL'
    if rsm_ok:             return 'RSM'
    return 'SMA50'


def _criteria_sort_key(sig: dict) -> int:
    return {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}.get(
        _criteria_label(sig), 9)


def send_discord(today_signals, pending_list, results, date_str, cfg):
    _load_env()
    url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    if not url:
        print('  DISCORD_WEBHOOK not set — skipping.')
        return

    date_fmt    = date_str.replace('_', '-')
    n_watchlist = len(pending_list)
    n_breakout  = len(today_signals)

    # Header: Ticker | T | Criteria | Level | Close | RVol | RSM | STR
    HDR = f"{'Ticker':<7}  {'T':<3}  {'Criteria':<6}  {'Level':>7}  {'Close':>7}  {'RVol':>6}  {'RSM':>4}  {'STR':>5}"
    DIV = "─" * len(HDR)

    if today_signals:
        rows = []
        # Sort: Prime first, then STR, RVOL, RSM, SMA50
        for s in sorted(today_signals, key=lambda x: (_criteria_sort_key(x), x['ticker'])):
            t       = s['ticker'].replace('.BK', '')
            kind    = 'Hz' if s.get('kind') == 'hz' else 'TL'
            crit    = _criteria_label(s)
            stretch = s.get('stretch', 0)
            str_disp= f'{stretch:.1f}x' if stretch else '—'
            rows.append(
                f"{t:<7}  {kind:<3}  {crit:<6}  "
                f"{s.get('bp',0):>7.2f}  {s.get('close',0):>7.2f}  "
                f"{s.get('rvol',0):>5.1f}x  {s.get('rsm',0):>4.0f}  {str_disp:>5}"
            )
        signal_block = "\n".join(rows)
    else:
        signal_block = "No breakout signals today."

    msg = (
        f"**BREAKOUT SCANNER  |  {date_fmt}**\n"
        f"`{n_watchlist} watchlist  ·  {n_breakout} breakout{'s' if n_breakout != 1 else ''}`\n"
        f"\n"
        f"```\n{HDR}\n{DIV}\n{signal_block}\n```\n"
        f"{CHART_URL}"
    )

    ok = _post(url, msg)
    print(f'  {"✅ Discord sent" if ok else "❌ Discord failed"} — {n_breakout} breakouts')