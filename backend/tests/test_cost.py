"""Regression test: /api/cost totals must reconcile exactly with
/api/stats/dashboard for the same window.

Before this fix, /api/cost filtered SessionSummaryRow by started_at only,
while /api/stats/dashboard (and repo_stats.fetch_real_stats) attribute a
session to a window by its last-event timestamp (falling back to
started_at) -- see app.services.stats_window.window_predicate. A
long-running session started outside the 7-day window but still updating
inside it was counted on the dashboard and silently dropped from /api/cost.

Also covers the additive `tracked` field on /api/cost's byRepo entries:
untracked Claude Code projects (any repo name not in the registered repo
list) must still be included in byRepo and in the totals -- only the
`tracked` flag distinguishes them.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from app.db import init_db
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    """AsyncClient with a fresh isolated DB and one tracked repo registered.
    Lifespan is NOT triggered.
    """
    monkeypatch.setenv("REPO_ROOTS", "/fake/root/tracked-repo")
    from app import config
    config.get_settings.cache_clear()

    import app.db as _db_module
    _db_module._engine = None
    _db_module._sessionmaker = None

    await init_db()
    from app.main import create_app
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c
    config.get_settings.cache_clear()


async def _seed(now: datetime) -> None:
    from app.db import _sessionmaker

    rows = [
        # Ordinary tracked-repo session, fully inside the 7-day window by
        # both started_at and last_event_at.
        SessionSummaryRow(
            session_id="tracked-normal",
            repo="tracked-repo",
            started_at=now - timedelta(days=1),
            last_event_at=now - timedelta(hours=23),
            status="completed",
            tokens=1_000,
            cost=1.0,
            edits=1,
            file_path="a.jsonl",
        ),
        # The reconciliation bug case: started well outside the window but
        # still updating right now -- a started_at-only filter drops this
        # session entirely; window_predicate (last-event-attributed) keeps
        # it, matching the dashboard.
        SessionSummaryRow(
            session_id="tracked-longrunning",
            repo="tracked-repo",
            started_at=now - timedelta(days=21),
            last_event_at=now,
            status="running",
            tokens=5_000_000,
            cost=50.0,
            edits=10,
            file_path="b.jsonl",
        ),
        # Untracked project -- not in REPO_ROOTS -- still real spend inside
        # the window.
        SessionSummaryRow(
            session_id="untracked-normal",
            repo="untracked-repo",
            started_at=now - timedelta(days=2),
            last_event_at=now - timedelta(days=1, hours=23),
            status="completed",
            tokens=2_000,
            cost=2.0,
            edits=0,
            file_path="c.jsonl",
        ),
        # Outside the window entirely on both sides -- must be excluded from
        # both endpoints' totals.
        SessionSummaryRow(
            session_id="tracked-lastweek",
            repo="tracked-repo",
            started_at=now - timedelta(days=10),
            last_event_at=now - timedelta(days=9, hours=23),
            status="completed",
            tokens=200,
            cost=0.2,
            edits=1,
            file_path="d.jsonl",
        ),
    ]
    async with _sessionmaker() as session:
        session.add_all(rows)
        session.add(
            SubagentCallRow(
                session_id="tracked-normal",
                agent_type="reviewer",
                repo="tracked-repo",
                tokens=300,
                cost=0.3,
                started_at=now - timedelta(hours=5),
                file_path="a-sub.jsonl",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_cost_and_dashboard_totals_reconcile(client: httpx.AsyncClient) -> None:
    from app.services.live_agents import get_tracker
    await get_tracker().reset()

    now = datetime.now(tz=UTC)
    await _seed(now)

    cost_res = await client.get("/api/cost?days=7")
    assert cost_res.status_code == 200
    cost = cost_res.json()

    dash_res = await client.get("/api/stats/dashboard")
    assert dash_res.status_code == 200
    dashboard = dash_res.json()

    assert dashboard["tokens"]["thisWeek"] == cost["totalTokens"]
    assert round(dashboard["cost"]["thisWeek"], 2) == cost["totalCost"]

    # Exact total: tracked-normal + tracked-longrunning + untracked-normal +
    # the subagent row. The long-running session's full total must be
    # included (proves the window fix), and tracked-lastweek's 200
    # tokens/$0.20 must be EXCLUDED (still outside the window on both sides).
    assert cost["totalTokens"] == 1_000 + 5_000_000 + 2_000 + 300
    assert cost["totalCost"] == pytest.approx(1.0 + 50.0 + 2.0 + 0.3, abs=1e-6)

    by_repo = {r["repo"]: r for r in cost["byRepo"]}
    assert by_repo["tracked-repo"]["tracked"] is True
    assert by_repo["untracked-repo"]["tracked"] is False
    # Untracked spend is included in byRepo and (transitively) in totals --
    # not silently dropped just because the repo isn't registered.
    assert by_repo["untracked-repo"]["tokens"] == 2_000
    assert by_repo["untracked-repo"]["cost"] == pytest.approx(2.0)

    # Subagent spend (started_at-windowed, per stats.py) folds into the
    # tracked repo's totals too.
    assert by_repo["tracked-repo"]["tokens"] == 1_000 + 5_000_000 + 300
