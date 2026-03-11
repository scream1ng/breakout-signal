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
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            return
    print('  No .env found. Tried:')
    for p in candidates:
        print(f'    {p}')


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
    if sig.get('rsm_ok') and sig.get('rvol_ok'):
        return 'Full'
    if sig.get('rvol_ok') and not sig.get('rsm_ok'):
        return 'No RSM'
    return 'Regime'


def send_discord(today_signals, pending_list, results, date_str, cfg):
    _load_env()
    url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    if not url:
        print('  DISCORD_WEBHOOK not set — skipping.')
        return

    date_fmt    = date_str.replace('_', '-')
    n_regime    = len(results)
    n_watchlist = len(pending_list)
    n_breakout  = len(today_signals)

    HDR = f"{'Ticker':<7}  {'T':<3}  {'Criteria':<8}  {'Level':>7}  {'Close':>7}  {'RVol':>6}  {'RSM':>4}  {'ATR':>5}"
    DIV = "─" * len(HDR)

    if today_signals:
        rows = []
        for s in sorted(today_signals, key=lambda x: x['ticker']):
            t       = s['ticker'].replace('.BK', '')
            kind    = 'Hz' if s.get('kind') == 'hz' else 'TL'
            crit    = _criteria_label(s)
            close   = s.get('close', 0)
            atr_pct = (s.get('atr', 0) / close * 100) if close else 0
            rows.append(
                f"{t:<7}  {kind:<3}  {crit:<8}  "
                f"{s.get('bp',0):>7.2f}  {close:>7.2f}  "
                f"{s.get('rvol',0):>5.1f}x  {s.get('rsm',0):>4.0f}  {atr_pct:>4.1f}%"
            )
        signal_block = "\n".join(rows)
    else:
        signal_block = "No breakout signals today."

    msg = (
        f"**PB Scanner  |  {date_fmt}**\n"
        f"`{n_regime} above SMA50  ·  {n_watchlist} watchlist  ·  {n_breakout} breakout{'s' if n_breakout != 1 else ''}`\n"
        f"\n"
        f"```\n{HDR}\n{DIV}\n{signal_block}\n```\n"
        f"{CHART_URL}"
    )

    ok = _post(url, msg)
    print(f'  {"✅ Discord sent" if ok else "❌ Discord failed"} — {n_breakout} breakouts')