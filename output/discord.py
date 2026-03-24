"""
discord.py — Send daily scan to Discord webhook.
Reads DISCORD_WEBHOOK from .env or environment.
Splits messages to avoid 2000-char Discord limit.
"""

import os

CHART_URL = "https://scream1ng.github.io/breakout-signal/"
DISCORD_LIMIT = 1900  # safe buffer below 2000


def _load_env():
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
        os.path.join(os.getcwd(), '.env'),
    ]
    for path in candidates:
        if os.path.exists(path):
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


def _post_chunks(url: str, chunks: list[str]) -> bool:
    """Post multiple messages sequentially."""
    import time
    ok = True
    for chunk in chunks:
        if not _post(url, chunk):
            ok = False
        time.sleep(0.5)  # avoid rate limit
    return ok


# ANSI color codes for Discord ```ansi blocks
# Format: \033[{style};{color}m  (style: 0=normal,1=bold | fg: 30-37, 90-97)
_ANSI = {
    'Prime': '\033[1;35m',   # bold magenta
    'STR':   '\033[1;31m',   # bold red
    'RVOL':  '\033[1;34m',   # bold blue
    'RSM':   '\033[1;32m',   # bold green
    'SMA50': '\033[1;33m',   # bold yellow
    'RESET': '\033[0m',
}


def _criteria_label(sig: dict) -> str:
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

    date_fmt   = date_str.replace('_', '-')
    n_breakout = len(today_signals)
    n_watchlist= len(pending_list)

    # ── Header ──────────────────────────────────────────────────────────────
    HDR = f"{'Ticker':<8}  {'T':<3}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'RVol':>6}  {'RSM':>4}  {'STR':>5}"
    DIV = "─" * len(HDR)

    header_msg = (
        f"**END OF DAY SCAN  |  {date_fmt}**\n"
        f"`{n_watchlist} watchlist  ·  {n_breakout} breakout{'s' if n_breakout != 1 else ''}`"
    )

    # ── Build rows sorted by criteria, blank lines between groups ─────────
    rows = []
    last_crit = None
    for s in sorted(today_signals, key=lambda x: (_criteria_sort_key(x), x['ticker'])):
        t        = s['ticker'].replace('.BK', '').replace('.AX', '')
        kind     = 'Hz' if s.get('kind') == 'hz' else 'TL'
        crit     = _criteria_label(s)
        stretch  = s.get('stretch', 0)
        str_disp = f'{stretch:.1f}x' if stretch else '—'
        col      = _ANSI.get(crit, '')
        rst      = _ANSI['RESET']
        if last_crit is not None and crit != last_crit:
            rows.append('')
        last_crit = crit
        rows.append(
            f"{col}{t:<8}{rst}  {kind:<3}  {col}{crit:<6}{rst}  "
            f"{s.get('bp',0):>8.2f}  {s.get('close',0):>8.2f}  "
            f"{s.get('rvol',0):>5.1f}x  {s.get('rsm',0):>4.0f}  {str_disp:>5}"
        )

    if not rows:
        rows = ["No breakout signals today."]

    # ── Chunk rows into messages under DISCORD_LIMIT ─────────────────────
    def make_block(row_list):
        return f"```ansi\n{HDR}\n{DIV}\n" + "\n".join(row_list) + f"\n{_ANSI['RESET']}```"

    chunks = []
    current_rows = []
    for row in rows:
        test_block = make_block(current_rows + [row])
        if len(test_block) > DISCORD_LIMIT and current_rows:
            while current_rows and current_rows[-1] == '':
                current_rows.pop()
            chunks.append(make_block(current_rows))
            current_rows = [row] if row else []
        else:
            current_rows.append(row)
    while current_rows and current_rows[-1] == '':
        current_rows.pop()
    if current_rows:
        chunks.append(make_block(current_rows))

    # ── Assemble final messages ──────────────────────────────────────────
    messages = [header_msg] + chunks + [CHART_URL]

    ok = _post_chunks(url, messages)
    print(f'  {"✅ Discord sent" if ok else "❌ Discord failed"} — {n_breakout} breakouts')