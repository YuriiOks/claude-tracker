"""Regression test: global /stats/dashboard totals must reconcile with the
sum of per-repo totals from repo_stats.fetch_real_stats().

Before this fix, /stats/dashboard filtered sessions by started_at >=
week_start only, while fetch_real_stats() OR'd in last_event_at >=
week_start. A long-running session started weeks ago but still updating
today was excluded from the global total (undercounted) while its ENTIRE
accumulated tokens/cost were counted in the per-repo total (correct, but
now mismatched against the global figure). Both now use the same
last-event-attributed window (see app.services.stats_window).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from app.db import init_db
from app.models.session_summary import SessionSummaryRow


@pytest_asyncio.fixture
async def client():
    """AsyncClient with a fresh isolated DB. Lifespan is NOT triggered."""
    import app.db as _db_module
    _db_module._engine = None
    _db_module._sessionmaker = None

    await init_db()
    from app.main import create_app
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed(now: datetime) -> None:
    from app.db import _sessionmaker

    rows = [
        # Ordinary session, fully inside "this week" by both started_at and
        # last_event_at.
        SessionSummaryRow(
            session_id="repo-a-normal",
            repo="repo-a",
            started_at=now - timedelta(days=2),
            last_event_at=now - timedelta(days=2, hours=-1),
            status="completed",
            tokens=1_000,
            cost=1.0,
            edits=1,
            file_path="a.jsonl",
        ),
        # The bug case: started 3 weeks ago (outside a started_at-only week
        # window) but still updating right now -- large accumulated total.
        SessionSummaryRow(
            session_id="repo-b-longrunning",
            repo="repo-b",
            started_at=now - timedelta(days=21),
            last_event_at=now,
            status="running",
            tokens=5_000_000,
            cost=50.0,
            edits=10,
            file_path="b.jsonl",
        ),
        # Purely "last week" -- excluded from this week's window on both sides.
        SessionSummaryRow(
            session_id="repo-c-lastweek",
            repo="repo-c",
            started_at=now - timedelta(days=10),
            last_event_at=now - timedelta(days=10, hours=-1),
            status="completed",
            tokens=200,
            cost=2.0,
            edits=1,
            file_path="c.jsonl",
        ),
    ]
    async with _sessionmaker() as session:
        session.add_all(rows)
        await session.commit()


@pytest.mark.asyncio
async def test_dashboard_and_repo_totals_reconcile(client: httpx.AsyncClient) -> None:
    from app.services.live_agents import get_tracker
    await get_tracker().reset()

    now = datetime.now(tz=UTC)
    await _seed(now)

    res = await client.get("/api/stats/dashboard")
    assert res.status_code == 200
    dashboard = res.json()

    from app.services.repo_stats import fetch_real_stats
    per_repo = await fetch_real_stats()

    sum_tokens_week = sum(s.tokens_week for s in per_repo.values())
    sum_cost_week = sum(s.cost_week for s in per_repo.values())
    sum_sessions_week = sum(s.sessions_week for s in per_repo.values())

    assert dashboard["tokens"]["thisWeek"] == sum_tokens_week
    assert round(dashboard["cost"]["thisWeek"], 2) == round(sum_cost_week, 2)
    assert dashboard["sessions"]["today"] >= 0  # sanity — today uses a separate window
    assert sum_sessions_week == 2  # repo-a-normal + repo-b-longrunning, not repo-c

    # The long-running session's full total must be attributed to "this
    # week" per-repo, matching what the global aggregate now also includes.
    assert per_repo["repo-b"].tokens_week == 5_000_000
    assert dashboard["tokens"]["thisWeek"] >= 5_000_000

    # repo-c is excluded from "this week" everywhere, but shows up in
    # "last week" on both the global and per-repo side.
    assert per_repo["repo-c"].tokens_week == 0
    assert per_repo["repo-c"].tokens_last_week == 200
    assert dashboard["tokens"]["lastWeek"] >= 200
