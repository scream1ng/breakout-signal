"""
app/notifications/discord.py — Discord ops-only alerts
=======================================================
Discord is no longer the primary signal channel (LINE is).
It receives:
  - Job failure alerts (send_job_failure)
  - System-level warnings that require immediate ops attention

Signal alerts (intraday, EOD, fakeout) → app/notifications/line.py
"""

import logging
import time

import requests

from app.config import DISCORD_WEBHOOK

logger = logging.getLogger(__name__)


def _post(payload: dict) -> bool:
    if not DISCORD_WEBHOOK:
        return False
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if r.status_code not in (200, 204):
            logger.warning('Discord error %s: %s', r.status_code, r.text[:120])
            return False
        return True
    except Exception as exc:
        logger.warning('Discord post failed: %s', exc)
        return False


def send_job_failure(job_name: str, error: str) -> bool:
    """Red embed — posted when a scheduled job raises an exception."""
    embed = {
        'color': 0xED4245,
        'author': {'name': f'⚠ Job failed · {job_name}'},
        'title': 'Scheduled job error',
        'description': f'```\n{error[:1000]}\n```',
    }
    ok = _post({'embeds': [embed]})
    time.sleep(0.4)
    return ok


def send_system_alert(title: str, message: str) -> bool:
    """Orange embed — generic ops system alert."""
    embed = {
        'color': 0xFAA61A,
        'author': {'name': '🔔 System alert'},
        'title': title,
        'description': message[:1800],
    }
    ok = _post({'embeds': [embed]})
    time.sleep(0.4)
    return ok
