"""Dashboard stats — real-time aggregates over SessionSummaryRow.

All metrics computed from the SQLite cache; deltas are real comparisons
against the prior period; sparkline buckets the last 24 hours.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from app.models.session_hour import SessionHourRow
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow
from app.services.ingest import SUBAGENT_HOUR_PREFIX
from app.services.live_agents import get_tracker
from app.services.stats_window import window_predicate

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
        # Include status="running" so a session that started yesterday but is
        # still active today is counted (same logic as repo_stats.py).
        today_id_rows = (await session.execute(
            select(SessionSummaryRow.session_id)
            .where(
                or_(
                    SessionSummaryRow.started_at >= today_start,
                    # Only count running sessions active today — avoids stale
                    # unclosed sessions from previous days inflating the count.
                    (
                        (SessionSummaryRow.status == "running")
                        & (SessionSummaryRow.last_event_at >= today_start)
                    ),
                )
            )
        )).scalars().all()
        sessions_today = len(today_id_rows)
        # Dedup against the live tracker: the DB query above already counts
        # running sessions active today, so only add a tracker entry if its
        # session was NOT already counted there (matched on the 8-char
        # sessionId prefix the tracker exposes, see live_agents.snapshot).
        # This avoids double-counting every active repo by >=1.
        today_id_prefixes = {sid[:8] for sid in today_id_rows}
        for entry in active_snapshot:
            started_raw = entry.get("startedAt") or ""
            try:
                started = datetime.fromisoformat(started_raw)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started >= today_start and entry.get("sessionId") not in today_id_prefixes:
                    sessions_today += 1
            except (ValueError, TypeError):
                pass
        sessions_yesterday = (await session.execute(
            select(func.count(SessionSummaryRow.session_id))
            .where(SessionSummaryRow.started_at >= yesterday_start,
                   SessionSummaryRow.started_at < today_start)
        )).scalar() or 0

        # ---- Tokens this week / last week ----
        # Attributed by last-event, not start time, so a long-running session
        # that started weeks ago but is still updating today lands in "this
        # week" here exactly like it does in repo_stats.fetch_real_stats —
        # otherwise the global total silently disagreed with the sum of
        # per-repo totals.
        tokens_this_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.tokens), 0))
            .where(window_predicate(week_start))
        )).scalar() or 0
        tokens_last_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.tokens), 0))
            .where(window_predicate(last_week_start, week_start))
        )).scalar() or 0

        # ---- Cost this week / last week ----
        cost_this_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.cost), 0.0))
            .where(window_predicate(week_start))
        )).scalar() or 0.0
        cost_last_week = (await session.execute(
            select(func.coalesce(func.sum(SessionSummaryRow.cost), 0.0))
            .where(window_predicate(last_week_start, week_start))
        )).scalar() or 0.0

        # ---- Fold in direct + workflow subagent tokens/cost ----
        # SubagentCallRow has no last-event timestamp of its own (calls are
        # short-lived — start and finish inside the same activity burst), so
        # these are windowed by started_at rather than window_predicate's
        # last-event rule. The two can only disagree by a call's own
        # duration (seconds to low minutes), negligible against a 7-day
        # window.
        sub_tokens_this_week = (await session.execute(
            select(func.coalesce(func.sum(SubagentCallRow.tokens), 0))
            .where(SubagentCallRow.started_at >= week_start)
        )).scalar() or 0
        sub_tokens_last_week = (await session.execute(
            select(func.coalesce(func.sum(SubagentCallRow.tokens), 0))
            .where(SubagentCallRow.started_at >= last_week_start,
                   SubagentCallRow.started_at < week_start)
        )).scalar() or 0
        sub_cost_this_week = (await session.execute(
            select(func.coalesce(func.sum(SubagentCallRow.cost), 0.0))
            .where(SubagentCallRow.started_at >= week_start)
        )).scalar() or 0.0
        sub_cost_last_week = (await session.execute(
            select(func.coalesce(func.sum(SubagentCallRow.cost), 0.0))
            .where(SubagentCallRow.started_at >= last_week_start,
                   SubagentCallRow.started_at < week_start)
        )).scalar() or 0.0
        tokens_this_week = int(tokens_this_week) + int(sub_tokens_this_week)
        tokens_last_week = int(tokens_last_week) + int(sub_tokens_last_week)
        cost_this_week = float(cost_this_week) + float(sub_cost_this_week)
        cost_last_week = float(cost_last_week) + float(sub_cost_last_week)

        # ---- 24-hour sparkline buckets ----
        # 24 one-hour buckets ending at the current hour
        spark_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        rows = (await session.execute(
            select(SessionSummaryRow.started_at, SessionSummaryRow.tokens,
                   SessionSummaryRow.cost)
            .where(SessionSummaryRow.started_at >= spark_start)
        )).all()
        sub_rows = (await session.execute(
            select(SubagentCallRow.started_at, SubagentCallRow.tokens, SubagentCallRow.cost)
            .where(SubagentCallRow.started_at >= spark_start)
        )).all()

        # ---- "Active in editor" sparkline: sessions whose [started_at,
        # last_event_at] interval overlaps each hourly bucket (not just
        # session-start counts, which is what buckets_sessions measures).
        active_rows = (await session.execute(
            select(SessionSummaryRow.started_at, SessionSummaryRow.last_event_at)
            .where(SessionSummaryRow.last_event_at >= spark_start,
                   SessionSummaryRow.started_at <= now)
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
    # Subagent/workflow spend counts toward the tokens/cost sparks (real
    # spend, wherever it came from) but not buckets_sessions -- a subagent
    # call is not a session of its own.
    for sub_started, sub_tokens, sub_cost in sub_rows:
        ts = sub_started if sub_started.tzinfo else sub_started.replace(tzinfo=UTC)
        delta_h = int((ts - spark_start).total_seconds() // 3600)
        if 0 <= delta_h < 24:
            buckets_tokens[delta_h] += sub_tokens or 0
            buckets_cost[delta_h] += sub_cost or 0.0

    buckets_active = [0] * 24
    for started, last_event in active_rows:
        s = started if started.tzinfo else started.replace(tzinfo=UTC)
        e = last_event if last_event.tzinfo else last_event.replace(tzinfo=UTC)
        for i in range(24):
            bucket_start = spark_start + timedelta(hours=i)
            if s < bucket_start + timedelta(hours=1) and e >= bucket_start:
                buckets_active[i] += 1

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
            "spark": buckets_active,
        },
        "asOf": now.isoformat(),
        "bucketStart": spark_start.isoformat(),
        "bucketSpanHours": 24,
    }


@router.get("/stats/heatmap")
async def heatmap_stats(tz: str = "UTC") -> dict:
    """7×24 session-count grid for the last 7 rolling days.

    Buckets sessions by LOCAL time (tz query param, e.g. "America/Sao_Paulo").
    Returns grid[day_index][hour] where day_index 0 = 6 days ago, 6 = today.
    Also returns per-repo 48h intensity arrays for the per-repo section.
    Each cell is a count of sessions active in that local hour.
    """
    from app.db import _ensure_engine, _sessionmaker
    _ensure_engine()
    if _sessionmaker is None:
        raise RuntimeError("DB not initialised")

    try:
        local_tz = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, KeyError):
        local_tz = UTC

    now = datetime.now(tz=UTC)
    local_now = now.astimezone(local_tz)

    # 7-day rolling window in local time, ending today.
    local_week_ago = (local_now - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Convert back to UTC for the DB WHERE clause.
    week_ago_utc = local_week_ago.astimezone(UTC)
    fortyeight_ago = now - timedelta(hours=48)

    async with _sessionmaker() as session:
        rows = (await session.execute(
            select(SessionHourRow.session_id, SessionHourRow.repo,
                   SessionHourRow.hour_ts, SessionHourRow.tokens)
            .where(
                SessionHourRow.hour_ts >= week_ago_utc,
                SessionHourRow.tokens > 0,
            )
        )).all()

    # Build 7×24 grid — one row per (session × local hour) from session_hour.
    grid = [[0] * 24 for _ in range(7)]
    token_grid = [[0] * 24 for _ in range(7)]
    repo_48h: dict[str, list[int]] = {}
    repo_tokens_48h: dict[str, list[int]] = {}

    for hour_key, repo_name, hour_ts, tokens in rows:
        # Subagent/workflow-agent hourly rows are keyed under a synthetic
        # SUBAGENT_HOUR_PREFIX id (see ingest._subagent_hour_key), not a real
        # session_id -- fold their spend into the token grids (real spend,
        # wherever it came from) but keep them out of the plain
        # session-activity grid/repo48h counts (a subagent call isn't "a
        # session").
        is_subagent = hour_key.startswith(SUBAGENT_HOUR_PREFIX)
        ts_utc = hour_ts if hour_ts.tzinfo else hour_ts.replace(tzinfo=UTC)
        ts_local = ts_utc.astimezone(local_tz)
        day_delta = (ts_local.date() - local_week_ago.date()).days
        if 0 <= day_delta < 7:
            if not is_subagent:
                grid[day_delta][ts_local.hour] += 1
            token_grid[day_delta][ts_local.hour] += tokens or 0
        # 48h intensity
        if ts_utc >= fortyeight_ago:
            if repo_name not in repo_48h:
                repo_48h[repo_name] = [0] * 48
                repo_tokens_48h[repo_name] = [0] * 48
            h_delta = int((ts_utc - fortyeight_ago).total_seconds() // 3600)
            if 0 <= h_delta < 48:
                if not is_subagent:
                    repo_48h[repo_name][h_delta] += 1
                repo_tokens_48h[repo_name][h_delta] += tokens or 0

    return {
        "grid": grid,
        "tokenGrid": token_grid,
        "dayLabels": [(local_week_ago + timedelta(days=i)).strftime("%a") for i in range(7)],
        "weekStart": local_week_ago.isoformat(),
        "repo48h": repo_48h,
        "repoTokens48h": repo_tokens_48h,
        "asOf": now.isoformat(),
    }
