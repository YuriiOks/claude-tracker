"""Wire identity for live events -- id + absolute ts + sessionId (additive fields).

Covers the additive-only contract added to LiveEvent / _event_to_wire /
_line_to_event: REST cold-start rows and WS pushes both need a stable id,
an absolute timestamp, and (for WS) the originating sessionId so the
frontend can dedup and detect gaps on reconnect.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest


@pytest.mark.asyncio
async def test_recent_endpoint_includes_id_and_absolute_ts_ordered() -> None:
    import app.db as db_mod
    from app.models.session_event import LiveEventRow

    # Force a fresh engine bound to this test's isolated DB_PATH -- app.db
    # caches _engine/_sessionmaker at module scope, so a stale handle from an
    # earlier test would otherwise leak rows across tests.
    db_mod._engine = None
    db_mod._sessionmaker = None
    await db_mod.init_db()
    async with db_mod._sessionmaker() as session:
        session.add(
            LiveEventRow(
                session_id="s1",
                repo="demo",
                ts=datetime(2026, 5, 10, 10, 0, 0),
                kind="tool",
                payload=json.dumps({"tool": "Read", "target": "x"}),
            )
        )
        session.add(
            LiveEventRow(
                session_id="s1",
                repo="demo",
                ts=datetime(2026, 5, 10, 10, 0, 5),
                kind="tool",
                payload=json.dumps({"tool": "Write", "target": "y"}),
            )
        )
        await session.commit()

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/live/recent")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    ids = [row["id"] for row in body]
    assert all(isinstance(i, int) for i in ids)
    assert ids == sorted(ids)
    for row in body:
        datetime.fromisoformat(row["ts"])  # raises on unparseable ISO-8601
    assert all(isinstance(row["t"], int) for row in body)


@pytest.mark.asyncio
async def test_event_to_wire_has_increasing_id_and_parseable_ts() -> None:
    from app.routers.live import _event_to_wire
    from app.services.jsonl_parser import ParsedEvent
    from app.services.live_stream import Hub

    hub = Hub()
    ev1 = ParsedEvent(datetime.now(tz=UTC), "demo", "tool", {"tool": "Read", "target": "x"})
    ev2 = ParsedEvent(datetime.now(tz=UTC), "demo", "tool", {"tool": "Write", "target": "y"})
    await hub.broadcast(ev1)
    await hub.broadcast(ev2)

    wire1 = _event_to_wire(ev1)
    wire2 = _event_to_wire(ev2)
    assert isinstance(wire1["id"], int)
    assert wire2["id"] == wire1["id"] + 1
    datetime.fromisoformat(wire1["ts"])  # raises on unparseable ISO-8601
    # WS ids are Hub-local, not DB primary keys -- they only need to be
    # unique + increasing per connection lifetime.


@pytest.mark.asyncio
async def test_emit_for_changes_attaches_session_id_to_payload(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from app import config
    from app.services.live_agents import get_tracker
    from app.services.live_stream import Hub, _emit_for_changes

    repo = tmp_path / "myrepo"
    repo.mkdir()
    jsonl = tmp_path / "abc.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "assistant",
                "sessionId": "sess-123",
                "cwd": str(repo),
                "timestamp": "2026-05-10T10:00:00Z",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}}
                    ]
                },
            }
        )
        + "\n"
    )

    monkeypatch.setenv("REPO_ROOTS", str(repo))
    config.get_settings.cache_clear()
    await get_tracker().reset()

    hub = Hub()
    queue = await hub.subscribe()
    await _emit_for_changes([jsonl], hub)

    ev = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert ev.payload["sessionId"] == "sess-123"
    assert ev.payload["tool"] == "Read"


def test_line_to_event_omits_session_id_when_absent() -> None:
    from pathlib import Path

    from app.services.live_stream import _line_to_event

    obj = {
        "type": "assistant",
        "cwd": "/tmp/myrepo",
        "timestamp": "2026-05-10T10:00:00Z",
        "message": {
            "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/x.py"}}]
        },
    }
    ev = _line_to_event(obj, [Path("/tmp/myrepo")])
    assert ev is not None
    assert "sessionId" not in ev.payload


@pytest.mark.asyncio
async def test_recent_endpoint_includes_session_id_from_row() -> None:
    """R-BE-29 — /api/live/recent must carry sessionId (LiveEvent.session_id,
    alias sessionId), sourced from the persisted row's own session_id column
    rather than the JSONL payload, so cold-start rows attribute correctly.
    """
    import app.db as db_mod
    from app.models.session_event import LiveEventRow

    db_mod._engine = None
    db_mod._sessionmaker = None
    await db_mod.init_db()
    async with db_mod._sessionmaker() as session:
        session.add(
            LiveEventRow(
                session_id="sess-abc123",
                repo="demo",
                ts=datetime(2026, 5, 10, 10, 0, 0),
                kind="tool",
                payload=json.dumps({"tool": "Read", "target": "x"}),
            )
        )
        await session.commit()

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/live/recent")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["sessionId"] == "sess-abc123"


@pytest.mark.asyncio
async def test_emit_for_changes_derives_delegate_from_agent_name(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-BE-27 — the live tailer's delegate "from" must be derived from the
    transcript's agentName (mirroring jsonl_parser.parse_jsonl), not
    hardcoded to "main".
    """
    import asyncio

    from app import config
    from app.services.live_agents import get_tracker
    from app.services.live_stream import Hub, _emit_for_changes

    repo = tmp_path / "myrepo"
    repo.mkdir()
    jsonl = tmp_path / "abc.jsonl"
    lines = [
        {
            "type": "agent-name",
            "agentName": "backend-engineer",
            "sessionId": "sess-456",
            "cwd": str(repo),
            "timestamp": "2026-05-10T10:00:00Z",
        },
        {
            "type": "assistant",
            "sessionId": "sess-456",
            "cwd": str(repo),
            "timestamp": "2026-05-10T10:00:01Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Task",
                        "input": {"subagent_type": "react-engineer", "prompt": "wire it up"},
                    }
                ]
            },
        },
    ]
    jsonl.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")

    monkeypatch.setenv("REPO_ROOTS", str(repo))
    config.get_settings.cache_clear()
    await get_tracker().reset()

    hub = Hub()
    queue = await hub.subscribe()
    await _emit_for_changes([jsonl], hub)

    ev = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert ev.kind == "delegate"
    assert ev.payload["from"] == "backend-engineer"
    assert ev.payload["to"] == "react-engineer"
