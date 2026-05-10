"""Human-friendly formatters used in the API responses."""
from __future__ import annotations

from datetime import datetime, timedelta


def fmt_duration(start: datetime, end: datetime) -> str:
    delta: timedelta = end - start
    total = int(delta.total_seconds())
    if total < 0:
        total = 0
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"


def fmt_started(ts: datetime, now: datetime | None = None) -> str:
    """Match data.js: 'HH:MM' for today, 'yesterday HH:MM', else short date."""
    now = now or datetime.now(tz=ts.tzinfo)
    delta = (now.date() - ts.date()).days
    hhmm = ts.strftime("%H:%M")
    if delta <= 0:
        return hhmm
    if delta == 1:
        return f"yesterday {hhmm}"
    return ts.strftime("%Y-%m-%d %H:%M")
