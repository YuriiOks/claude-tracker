"""Compute real RepoStats for each tracked repo from the session_summary table.

Runs as one combined query (cheaper than N round-trips) and returns a dict
keyed by repo name → RepoStats. Used to enrich the `/api/repos` response.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.session_summary import SessionSummaryRow
from app.schemas.repo import RepoStats


def _fmt_avg(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "—"
    m = int(seconds // 60)
    if m < 1: return f"{int(seconds)}s"
    if m < 60: return f"{m}m"
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
        # Today's session count per repo
        today_rows = (await session.execute(
            select(SessionSummaryRow.repo, func.count(SessionSummaryRow.session_id))
            .where(SessionSummaryRow.started_at >= today)
            .group_by(SessionSummaryRow.repo)
        )).all()
        today_map = {r[0]: r[1] for r in today_rows}

        # Week aggregates per repo (sessions, tokens, cost, edits, avg duration)
        week_rows = (await session.execute(
            select(
                SessionSummaryRow.repo,
                func.count(SessionSummaryRow.session_id),
                func.coalesce(func.sum(SessionSummaryRow.tokens), 0),
                func.coalesce(func.sum(SessionSummaryRow.cost), 0.0),
                func.coalesce(func.sum(SessionSummaryRow.edits), 0),
                func.avg(
                    func.julianday(SessionSummaryRow.last_event_at)
                    - func.julianday(SessionSummaryRow.started_at)
                ),
            )
            .where(SessionSummaryRow.started_at >= week_start)
            .group_by(SessionSummaryRow.repo)
        )).all()

        for repo_name, sessions_w, tokens_w, cost_w, edits_w, avg_jd in week_rows:
            avg_seconds = (avg_jd or 0) * 86400  # julianday delta → seconds
            out[repo_name] = RepoStats(
                sessionsToday=today_map.get(repo_name, 0),
                sessionsWeek=sessions_w or 0,
                tokensWeek=int(tokens_w or 0),
                costWeek=round(float(cost_w or 0.0), 2),
                filesEdited=edits_w or 0,
                avgSession=_fmt_avg(avg_seconds),
            )

        # Repos with sessions today but none this week (unlikely) — backfill
        for repo_name, n in today_map.items():
            if repo_name not in out:
                out[repo_name] = RepoStats(sessionsToday=n)

    return out
