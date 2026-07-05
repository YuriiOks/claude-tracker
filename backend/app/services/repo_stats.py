"""Compute real RepoStats for each tracked repo from the session_summary table.

Runs as one combined query (cheaper than N round-trips) and returns a dict
keyed by repo name → RepoStats. Used to enrich the `/api/repos` response.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select

from app.models.session_summary import SessionSummaryRow
from app.schemas.repo import RepoStats
from app.services.live_agents import get_tracker


def _fmt_avg(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "—"
    m = int(seconds // 60)
    if m < 1:
        return f"{int(seconds)}s"
    if m < 60:
        return f"{m}m"
    h = m // 60
    return f"{h}h {m % 60}m"


async def fetch_real_stats() -> dict[str, RepoStats]:
    """Returns { repo_name → RepoStats } computed from session_summary."""
    from app.db import _ensure_engine, _sessionmaker
    _ensure_engine()
    if _sessionmaker is None:
        return {}

    now = datetime.now(tz=UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Rolling 7-day window — more meaningful than ISO Mon-Sun (which on
    # a fresh Monday would show zero activity for everyone).
    week_start = now - timedelta(days=7)

    out: dict[str, RepoStats] = {}
    async with _sessionmaker() as session:
        # Today's sessions per repo (fetch ids, not just counts, so the
        # live-tracker dedup below can check membership).
        today_rows = (await session.execute(
            select(SessionSummaryRow.repo, SessionSummaryRow.session_id)
            .where(
                or_(
                    SessionSummaryRow.started_at >= today,
                    # Count a running session as "today" only if it was active
                    # today — prevents stale/crashed sessions from inflating counts.
                    (
                        (SessionSummaryRow.status == "running")
                        & (SessionSummaryRow.last_event_at >= today)
                    ),
                )
            )
        )).all()
        today_map: dict[str, int] = {}
        today_ids_by_repo: dict[str, set[str]] = {}
        for repo_name, session_id in today_rows:
            today_map[repo_name] = today_map.get(repo_name, 0) + 1
            today_ids_by_repo.setdefault(repo_name, set()).add(session_id[:8])

        # Build live_today_map from the in-memory tracker (running sessions not
        # yet ingested). Dedup on session_id: the DB query above already counts
        # running sessions active today, so only add a tracker entry if its
        # session was NOT already counted there (matched on the 8-char
        # sessionId prefix the tracker exposes, see live_agents.snapshot). This
        # avoids double-counting every active repo by >=1.
        live_today_map: dict[str, int] = {}
        for entry in await get_tracker().snapshot():
            repo_name = entry.get("repo") or ""
            started_raw = entry.get("startedAt") or ""
            sid_prefix = entry.get("sessionId") or ""
            if not repo_name or not started_raw:
                continue
            try:
                started = datetime.fromisoformat(started_raw)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started >= today and sid_prefix not in today_ids_by_repo.get(repo_name, set()):
                    live_today_map[repo_name] = live_today_map.get(repo_name, 0) + 1
            except ValueError:
                pass

        # Week aggregates per repo (sessions, tokens, cost, edits, avg duration).
        # Include any session active within the window: either started this week
        # OR still running/updated this week (long-running sessions).
        week_rows = (await session.execute(
            select(
                SessionSummaryRow.repo,
                func.count(SessionSummaryRow.session_id),
                func.coalesce(func.sum(SessionSummaryRow.tokens), 0),
                func.coalesce(func.sum(SessionSummaryRow.cost), 0.0),
                func.coalesce(func.sum(SessionSummaryRow.edits), 0),
                # Avg only over sessions that STARTED this week and are completed.
                # • Running sessions have no final duration yet.
                # • Old sessions (started months ago, still referenced by new subagents)
                #   have durations spanning months — they pollute the avg badly.
                func.avg(
                    func.julianday(SessionSummaryRow.last_event_at)
                    - func.julianday(SessionSummaryRow.started_at)
                ).filter(
                    (SessionSummaryRow.status != "running")
                    & (SessionSummaryRow.started_at >= week_start)
                ),
            )
            .where(
                or_(
                    SessionSummaryRow.started_at >= week_start,
                    SessionSummaryRow.last_event_at >= week_start,
                )
            )
            .group_by(SessionSummaryRow.repo)
        )).all()

        # 24-bucket spark for each repo (last 24h, hourly session counts)
        spark_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        spark_rows = (await session.execute(
            select(SessionSummaryRow.repo, SessionSummaryRow.started_at)
            .where(SessionSummaryRow.started_at >= spark_start)
        )).all()

        # Build per-repo 24-bucket arrays
        spark_map: dict[str, list[int]] = {}
        for repo_name, ts in spark_rows:
            if repo_name not in spark_map:
                spark_map[repo_name] = [0] * 24
            ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            delta_h = int((ts_utc - spark_start).total_seconds() // 3600)
            if 0 <= delta_h < 24:
                spark_map[repo_name][delta_h] += 1

        for repo_name, sessions_w, tokens_w, cost_w, edits_w, avg_jd in week_rows:
            avg_seconds = (avg_jd or 0) * 86400  # julianday delta → seconds
            out[repo_name] = RepoStats(
                sessionsToday=today_map.get(repo_name, 0) + live_today_map.get(repo_name, 0),
                sessionsWeek=sessions_w or 0,
                tokensWeek=int(tokens_w or 0),
                costWeek=round(float(cost_w or 0.0), 2),
                filesEdited=edits_w or 0,
                avgSession=_fmt_avg(avg_seconds),
                spark=spark_map.get(repo_name, [0] * 24),
            )

        # Repos with sessions today but none this week (unlikely) — backfill
        for repo_name, n in today_map.items():
            if repo_name not in out:
                out[repo_name] = RepoStats(
                    sessionsToday=n + live_today_map.get(repo_name, 0),
                    spark=spark_map.get(repo_name, [0] * 24),
                )

    # Repos only visible in the live tracker (not yet in DB at all) — stub entry
    for repo_name, live_count in live_today_map.items():
        if repo_name not in out:
            out[repo_name] = RepoStats(sessionsToday=live_count)

    return out
