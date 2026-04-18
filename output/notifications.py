"""
notifications.py — Centralized notification logic (Discord, Telegram, LINE).
Currently implements Discord webhook messaging.
"""

import os
import requests
import time

def get_chart_url():
    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    return f"https://{domain}/" if domain else "https://breakout-signal.up.railway.app/"
MESSAGE_LIMIT = 1900  # safe buffer under 2000 chars

# ANSI color codes for Discord ```ansi blocks
_ANSI = {
    'Prime': '\033[1;35m',   # bold magenta
    'STR':   '\033[1;31m',   # bold red
    'RVOL':  '\033[1;34m',   # bold blue
    'RSM':   '\033[1;32m',   # bold green
    'SMA50': '\033[1;33m',   # bold yellow
    'RESET': '\033[0m',
}

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
    try:
        r = requests.post(url, json={'content': text}, timeout=10)
        if r.status_code not in (200, 204):
            print(f'  Notification error: {r.status_code} {r.text[:100]}')
            return False
        return True
    except Exception as e:
        print(f'  Notification error: {e}')
        return False

def _post_chunks(url: str, chunks: list[str]) -> bool:
    ok = True
    for chunk in chunks:
        if not _post(url, chunk):
            ok = False
        time.sleep(0.5)
    return ok

# ── Criteria Helpers ──────────────────────────────────────────────────────────

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

# ── EOD Alerts (main.py) ──────────────────────────────────────────────────────

def send_eod_alert(today_signals, pending_list, results, date_str, cfg):
    """Formats and sends the End of Day summary."""
    _load_env()
    
    # Check what platform to send to
    discord_url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    
    if not discord_url:
        print('  DISCORD_WEBHOOK not set — skipping notifications.')
        return

    date_fmt   = date_str.replace('_', '-')
    n_breakout = len(today_signals)
    n_watchlist= len(pending_list)

    HDR = f"{'Ticker':<8}  {'T':<10}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'RVol':>9}  {'RSM':>7}  {'STR':>8}"
    DIV = "─" * len(HDR)

    header_msg = (
        f"**END OF DAY SCAN  |  {date_fmt}**\n"
        f"`{n_watchlist} watchlist  ·  {n_breakout} breakout{'s' if n_breakout != 1 else ''}`"
    )

    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min  = cfg.get('rs_momentum_min', 70)
    GG = '\033[1;32m'; RR = '\033[1;31m'; RST2 = '\033[0m'
    def tk(ok): return f'{GG}✓{RST2}' if ok else f'{RR}✗{RST2}'

    rows = []
    last_crit = None
    for s in sorted(today_signals, key=lambda x: (_criteria_sort_key(x), x['ticker'])):
        t        = s['ticker'].replace('.BK', '').replace('.AX', '')
        crit     = _criteria_label(s)
        stretch  = s.get('stretch', 0)
        rvol     = s.get('rvol', 0)
        rsm      = s.get('rsm', 0)
        str_disp = f'{stretch:.1f}x' if stretch else '—'
        col      = _ANSI.get(crit, '')
        rst      = _ANSI['RESET']
        if last_crit is not None and crit != last_crit:
            rows.append('')
        last_crit = crit
        ang      = s.get('tl_angle')
        kind_lbl = f'TL ({ang:.0f}\u00b0)' if s.get('kind')=='tl' and ang is not None else ('TL' if s.get('kind')=='tl' else 'Hz')
        rvol_str = f'{rvol:>5.1f}x{tk(rvol >= rvol_min)}'
        rsm_str  = f'{rsm:>4.0f}{tk(rsm >= rsm_min)}'
        str_str  = f'{str_disp:>5}{tk(stretch <= 4)}'
        rows.append(
            f"{col}{t:<8}{rst}  {kind_lbl:<10}  {col}{crit:<6}{rst}  "
            f"{s.get('bp',0):>8.2f}  {s.get('close',0):>8.2f}  "
            f"{rvol_str}  {rsm_str}  {str_str}"
        )

    if not rows:
        rows = ["No breakout signals today."]

    def make_block(row_list):
        return f"```ansi\n{HDR}\n{DIV}\n" + "\n".join(row_list) + f"\n{_ANSI['RESET']}```"

    chunks = []
    current_rows = []
    for row in rows:
        test_block = make_block(current_rows + [row])
        if len(test_block) > MESSAGE_LIMIT and current_rows:
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

    if chunks:
        chunks[0] = f"{header_msg}\n{chunks[0]}"
        chunks[-1] = f"{chunks[-1]}\n**View charts:** {get_chart_url()}"
    messages = chunks
    
    # Dispatch
    if discord_url:
        ok = _post_chunks(discord_url, messages)
        print(f'  {"✅ Notification sent" if ok else "❌ Notification failed"} — {n_breakout} breakouts')


# ── Intraday Alerts (intraday.py) ─────────────────────────────────────────────

def send_intraday_alert(signals, now, cfg):
    """Formats and sends the Intraday breakout alert."""
    _load_env()
    
    discord_url = os.environ.get('DISCORD_WEBHOOK', '').strip()
    if not discord_url:
        print('  DISCORD_WEBHOOK not set — skipping notifications.')
        return

    date_str   = now.strftime('%Y-%m-%d')
    time_str   = now.strftime('%H:%M')
    n          = len(signals)

    HDR = f"{'Ticker':<8}  {'T':<10}  {'Crit':<6}  {'Level':>8}  {'Close':>8}  {'ProjRVol':>10}  {'RVol':>9}  {'RSM':>7}  {'STR':>8}"
    DIV = '─' * 90

    header_msg = (
        f"**⚡ INTRADAY SCAN  |  {date_str}  {time_str} BKK**\n"
        f"`{n} signal{'s' if n!=1 else ''}`"
    )

    GG = '\033[1;32m'; RR = '\033[1;31m'; RST2 = '\033[0m'
    def tk(ok): return f'{GG}✓{RST2}' if ok else f'{RR}✗{RST2}'
    rvol_min = cfg.get('rvol_min', 1.5)
    rsm_min  = cfg.get('rs_momentum_min', 70)

    sort_key = {'Prime': 0, 'STR': 1, 'RVOL': 2, 'RSM': 3, 'SMA50': 4}
    rows      = []
    last_crit = None
    for s in sorted(signals, key=lambda x: (sort_key.get(x['criteria'], 9), x['ticker'])):
        crit      = s['criteria']
        col       = _ANSI.get(crit, '')
        rst       = _ANSI['RESET']
        stretch   = s.get('stretch', 0)
        cur_rvol  = s.get('cur_rvol', 0)
        proj_rvol = s.get('proj_rvol', 0)
        rsm       = s.get('rsm', 0)
        str_disp  = f'{stretch:.1f}x' if stretch else '—'

        proj_str = f'{proj_rvol:>8.1f}x{tk(proj_rvol >= rvol_min)}'
        rvol_str = f'{cur_rvol:>5.1f}x{tk(cur_rvol  >= rvol_min)}'
        rsm_str  = f'{rsm:>4.0f}{tk(rsm >= rsm_min)}'
        str_str  = f'{str_disp:>5}{tk(stretch <= 4)}'

        if last_crit is not None and crit != last_crit:
            rows.append('')
        last_crit = crit
        ang      = s.get('tl_angle')
        kind_lbl = f"TL ({ang:.0f}\u00b0)" if s.get('kind')=='tl' and ang is not None else ('TL' if s.get('kind')=='tl' else 'Hz')
        rows.append(
            f"{col}{s['ticker']:<8}{rst}  {kind_lbl:<10}  {col}{crit:<6}{rst}  "
            f"{s['level']:>8.2f}  {s['close']:>8.2f}  "
            f"{proj_str}  {rvol_str}  {rsm_str}  {str_str}"
        )

    def make_block(row_list):
        return f"```ansi\n{HDR}\n{DIV}\n" + "\n".join(row_list) + f"\n{_ANSI['RESET']}```"

    chunks = []
    current_rows = []
    for row in rows:
        if len(make_block(current_rows + [row])) > MESSAGE_LIMIT and current_rows:
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

    if chunks:
        chunks[0] = f"{header_msg}\n{chunks[0]}"
    messages = chunks
    
    # Dispatch
    if discord_url:
        ok = _post_chunks(discord_url, messages)
        print(f'  {"✅ Notification sent" if ok else "❌ Notification failed"} — {n} signals')