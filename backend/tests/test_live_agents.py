from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_tracker_records_and_prunes() -> None:
    from app.services.live_agents import _Activity, get_tracker

    tracker = get_tracker()
    await tracker.reset()

    now = datetime.now(tz=UTC)
    await tracker.record("s1", "jupus", "delegate", {"to": "ai-developer"}, ts=now)
    await tracker.record("s1", "jupus", "tool", {"tool": "Read", "target": "x.py"}, ts=now)
    await tracker.record("s2", "anita", "tool", {"tool": "Bash", "target": "pytest"}, ts=now)

    snap = await tracker.snapshot()
    assert len(snap) == 2
    s1 = next(x for x in snap if x["sessionId"].startswith("s1"))
    assert s1["agent"] == "ai-developer"
    assert s1["currentTool"] == "Read"
    assert s1["currentTarget"] == "x.py"
    assert s1["secondsSinceLastEvent"] >= 0

    # Stale entries are pruned.
    tracker._sessions["s1"].last_seen_at = now - timedelta(seconds=200)
    snap2 = await tracker.snapshot()
    assert all(x["sessionId"][:2] != "s1" for x in snap2)


@pytest.mark.asyncio
async def test_endpoint_returns_active_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.services.live_agents import get_tracker
    tracker = get_tracker()
    await tracker.reset()
    await tracker.record(
        "abc-12345",
        "demo",
        "delegate",
        {"to": "tester"},
        ts=datetime.now(tz=UTC),
    )

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.get("/api/live/agents")
    assert res.status_code == 200
    body = res.json()
    assert body[0]["agent"] == "tester"
    assert body[0]["repo"] == "demo"
