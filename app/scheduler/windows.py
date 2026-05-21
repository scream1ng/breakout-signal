from __future__ import annotations

from datetime import datetime


INTRADAY_BKK_SLOTS = tuple(
    f'{hour:02d}:{minute:02d}'
    for hour in range(10, 17)
    for minute in (0, 15, 30, 45)
    if (10 * 60 + 30) <= (hour * 60 + minute) <= (12 * 60 + 30)
    or (14 * 60 + 0) <= (hour * 60 + minute) <= (16 * 60 + 15)
)
INTRADAY_BKK_SLOT_SET = frozenset(INTRADAY_BKK_SLOTS)

REVIEW_BKK_SLOTS = ('16:25',)
REVIEW_BKK_SLOT_SET = frozenset(REVIEW_BKK_SLOTS)

EOD_BKK_SLOT = '16:45'


def scheduler_slot_label(now: datetime) -> str:
    return now.strftime('%H:%M')


def is_allowed_intraday_scheduler_slot(now: datetime, *, review: bool = False) -> bool:
    slot = scheduler_slot_label(now)
    allowed = REVIEW_BKK_SLOT_SET if review else INTRADAY_BKK_SLOT_SET
    return slot in allowed
