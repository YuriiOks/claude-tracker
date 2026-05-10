"""WebSocket integration test — synthesize JSONL writes, verify hub broadcasts."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_hub_broadcast_to_subscribers() -> None:
    from app.services.live_stream import Hub
    from app.services.jsonl_parser import ParsedEvent
    from datetime import datetime, timezone

    hub = Hub()
    a = await hub.subscribe()
    b = await hub.subscribe()

    ev = ParsedEvent(datetime.now(tz=timezone.utc), "demo", "tool", {"tool": "Read", "target": "x"})
    await hub.broadcast(ev)

    assert (await asyncio.wait_for(a.get(), timeout=1.0)).kind == "tool"
    assert (await asyncio.wait_for(b.get(), timeout=1.0)).kind == "tool"

    await hub.unsubscribe(a)
    assert hub.subscribers == 1


def test_line_to_event_handles_command() -> None:
    from app.services.live_stream import _line_to_event

    obj = {
        "type": "user",
        "cwd": "/tmp/myrepo",
        "timestamp": "2026-05-10T10:00:00Z",
        "message": {"content": "/run-tests"},
    }
    ev = _line_to_event(obj, [Path("/tmp/myrepo")])
    assert ev is not None
    assert ev.kind == "command"
    assert ev.payload["cmd"] == "/run-tests"


def test_line_to_event_handles_tool_use() -> None:
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
    assert ev.kind == "tool"
    assert ev.payload["tool"] == "Read"
    assert ev.repo == "myrepo"


def test_line_to_event_skips_unknown() -> None:
    from app.services.live_stream import _line_to_event

    assert _line_to_event({"type": "weirdo", "timestamp": "2026-05-10T10:00:00Z"}, []) is None
