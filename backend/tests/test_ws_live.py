"""WebSocket integration test — synthesize JSONL writes, verify hub broadcasts."""
from __future__ import annotations

import asyncio
from datetime import UTC
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_hub_broadcast_to_subscribers() -> None:
    from datetime import datetime

    from app.services.jsonl_parser import ParsedEvent
    from app.services.live_stream import Hub

    hub = Hub()
    a = await hub.subscribe()
    b = await hub.subscribe()

    ev = ParsedEvent(datetime.now(tz=UTC), "demo", "tool", {"tool": "Read", "target": "x"})
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


@pytest.mark.asyncio
async def test_watch_loop_restarts_after_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unexpected exception out of watchfiles.awatch (e.g. an OSError from
    the underlying inotify/FSEvents backend) must not kill `_watch_loop` for
    good -- only asyncio.CancelledError (deliberate shutdown) may propagate.
    This proves the loop logs a warning and restarts the watch instead of
    dying, and keeps processing changes once the retry succeeds.
    """
    from app.services import live_stream

    monkeypatch.setattr(live_stream, "_WATCH_RESTART_BACKOFF_INITIAL_SEC", 0.01)
    monkeypatch.setattr(live_stream, "_ingest_signal_queue", asyncio.Queue())  # isolate from other tests

    changed_file = tmp_path / "restarted.jsonl"
    changed_file.write_text("")

    calls = {"n": 0}

    async def _raising_gen(*_args, **_kwargs):
        raise OSError("simulated watcher crash")
        yield  # pragma: no cover -- unreachable, but keeps this an async generator function

    async def _yielding_gen(*_args, **_kwargs):
        yield {("added", str(changed_file))}

    def fake_awatch(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _raising_gen()
        return _yielding_gen()

    monkeypatch.setattr(live_stream.watchfiles, "awatch", fake_awatch)

    hub = live_stream.Hub()
    # awatch's fake second generator yields exactly one change_set then ends
    # on its own, so a healthy _watch_loop returns cleanly on its own --
    # wait_for is just a safety net against a hang, not a real timeout.
    await asyncio.wait_for(live_stream._watch_loop(tmp_path, hub), timeout=2.0)

    assert calls["n"] >= 2, "awatch was not retried after the simulated crash"

    signaled: set[Path] = set()
    queue = live_stream.get_ingest_signal_queue()
    while not queue.empty():
        signaled.add(queue.get_nowait())
    assert changed_file in signaled
