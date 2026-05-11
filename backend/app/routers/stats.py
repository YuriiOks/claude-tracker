"""Dashboard stats — real-time aggregates over SessionSummaryRow.

All metrics computed from the SQLite cache; deltas are real comparisons
against the prior period; sparkline buckets the last 24 hours.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.models.session_summary import SessionSummaryRow
from app.services.live_agents import get_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["stats"])


def _pct_delta(current: float, previous: float) -> float | None:
    """Percent change current vs previous. None if previous is 0."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


@router.get("/stats/dashboard")
async def dashboard_stats() -> dict:
    """One-shot aggregator for the four dashboard metric cards.
    Returns totals + deltas + 24-bucket sparklines for each metric.
    """
    from app.db import _ensure_engine, _sessionmaker
    _ensure_engine()
    if _sessionmaker is None:
        raise RuntimeError("DB sessionmaker not initialised")

    now = datetime.now(tz=UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    # Rolling 7-day windows (not ISO weeks) — keeps the dashboard meaningful
    # on a fresh Monday morning when ISO-week-to-date would be empty.
    week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)

    # ---- Live count from in-memory tracker (no DB) ----
    active_snapshot = await get_tracker().snapshot()
    active_count = len(active_snapshot)

    async with _sessionmaker() as session:
        # ---- Sessions today / yesterday ----
        sessions_today = (await session.execute(
            select(func.count(SessionSummaryRow.session_id))
            .where(SessionSummaryRow.started_at >= today_start)
        )).scalar() or 0
        sessions_yesterday = (await session.execute(
            select(func.count(SessionSummaryRow.session_id))
            .where(SessionSummaryRow.started_at >= yesterday_start,
                   SessionSummaryRow.started_at < today_start)
        )).scalar() or 0

        # ---- Tokens this week / last week ----
        tokens_this_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.tokens), 0))
            .where(SessionSummaryRow.started_at >= week_start)
        )).scalar() or 0
        tokens_last_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.tokens), 0))
            .where(SessionSummaryRow.started_at >= last_week_start,
                   SessionSummaryRow.started_at < week_start)
        )).scalar() or 0

        # ---- Cost this week / last week ----
        cost_this_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.cost), 0.0))
            .where(SessionSummaryRow.started_at >= week_start)
        )).scalar() or 0.0
        cost_last_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.cost), 0.0))
            .where(SessionSummaryRow.started_at >= last_week_start,
                   SessionSummaryRow.started_at < week_start)
        )).scalar() or 0.0

        # ---- 24-hour sparkline buckets ----
        # 24 one-hour buckets ending at the current hour
        spark_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        rows = (await session.execute(
            select(SessionSummaryRow.started_at, SessionSummaryRow.tokens,
                   SessionSummaryRow.cost)
            .where(SessionSummaryRow.started_at >= spark_start)
        )).all()

    # Build hourly buckets in local order (oldest first)
    buckets_sessions = [0] * 24
    buckets_tokens = [0] * 24
    buckets_cost = [0.0] * 24
    for row in rows:
        ts = row[0] if row[0].tzinfo else row[0].replace(tzinfo=UTC)
        delta_h = int((ts - spark_start).total_seconds() // 3600)
        if 0 <= delta_h < 24:
            buckets_sessions[delta_h] += 1
            buckets_tokens[delta_h] += row[1] or 0
            buckets_cost[delta_h] += row[2] or 0.0

    # Already a rolling 7-day total, no projection needed.
    projected_tokens_eow = int(tokens_this_week)

    return {
        "sessions": {
            "today": sessions_today,
            "yesterday": sessions_yesterday,
            "deltaPct": _pct_delta(sessions_today, sessions_yesterday),
            "spark": buckets_sessions,
        },
        "tokens": {
            "thisWeek": int(tokens_this_week),
            "lastWeek": int(tokens_last_week),
            "projectedEow": projected_tokens_eow,
            "deltaPct": _pct_delta(tokens_this_week, tokens_last_week),
            "spark": buckets_tokens,
        },
        "cost": {
            "thisWeek": round(float(cost_this_week), 2),
            "lastWeek": round(float(cost_last_week), 2),
            "deltaPct": _pct_delta(cost_this_week, cost_last_week),
            "spark": [round(c, 4) for c in buckets_cost],
        },
        "active": {
            "count": active_count,
            "spark": buckets_sessions,  # reuse — visually meaningful
        },
        "asOf": now.isoformat(),
        "bucketStart": spark_start.isoformat(),
        "bucketSpanHours": 24,
    }
