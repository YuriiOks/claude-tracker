"""Shared time-window predicate for dashboard/repo stats aggregation.

Both `/stats/dashboard` and `fetch_real_stats()` bucket sessions into
this-week / last-week windows. A session is attributed to the window that
contains its *last activity*, not its start time — otherwise a long-running
session started weeks ago but still updating today either drops out of a
started_at-only filter (undercounting) or, if OR'd in on `last_event_at`
elsewhere, gets its entire accumulated total double-attributed to a stale
window. Using one predicate everywhere keeps global and per-repo totals
reconcilable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, func

from app.models.session_summary import SessionSummaryRow


def window_predicate(start: datetime, end: datetime | None = None) -> ColumnElement[bool]:
    """True if the session's last-event-attributed timestamp falls in [start, end).

    Falls back to started_at when last_event_at is unset. `end=None` means
    "start and everything after" (open-ended window).
    """
    ts = func.coalesce(SessionSummaryRow.last_event_at, SessionSummaryRow.started_at)
    if end is None:
        return ts >= start
    return (ts >= start) & (ts < end)
