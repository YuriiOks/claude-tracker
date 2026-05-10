"""Watchfiles-based JSONL tailer + asyncio pub/sub Hub for /ws/live.

Design:
  • Hub is a global singleton — clients subscribe() to receive a personal queue.
  • A single background task (start_watcher) runs watchfiles.awatch on
    projects_dir, reads only new bytes from each changed file, parses lines
    incrementally, and broadcasts each ParsedEvent to all subscribers.
  • Per-file byte offset is kept in a dict; new files start at 0.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import watchfiles

from app.config import get_settings
from app.services.jsonl_parser import ParsedEvent, parse_jsonl

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self, max_queue_per_client: int = 256) -> None:
        self._subs: list[asyncio.Queue[ParsedEvent]] = []
        self._max = max_queue_per_client
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def subscribe(self) -> asyncio.Queue[ParsedEvent]:
        q: asyncio.Queue[ParsedEvent] = asyncio.Queue(maxsize=self._max)
        async with self._lock:
            self._subs.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[ParsedEvent]) -> None:
        async with self._lock:
            try:
                self._subs.remove(q)
            except ValueError:
                pass

    async def broadcast(self, event: ParsedEvent) -> None:
        async with self._lock:
            dead: list[asyncio.Queue[ParsedEvent]] = []
            for q in self._subs:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("hub subscriber queue full; dropping client")
                    dead.append(q)
            for q in dead:
                try:
                    self._subs.remove(q)
                except ValueError:
                    pass

    @property
    def subscribers(self) -> int:
        return len(self._subs)

    def attach_task(self, task: asyncio.Task) -> None:
        self._task = task

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None


_HUB: Hub | None = None


def get_hub() -> Hub:
    global _HUB
    if _HUB is None:
        _HUB = Hub()
    return _HUB


# ---------------------------------------------------------------------------
# Tailer
# ---------------------------------------------------------------------------

# We avoid re-parsing each file from scratch on every change by tracking byte
# offsets. Each tail call returns the events emitted by the new bytes.

_offsets: dict[Path, int] = defaultdict(int)


def _tail_new_lines(path: Path) -> list[str]:
    """Read any unread bytes from path; return complete lines."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    offset = _offsets[path]
    if size <= offset:
        # File truncated or unchanged.
        if size < offset:
            _offsets[path] = 0
            offset = 0
        else:
            return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            chunk = fh.read()
    except OSError:
        return []
    _offsets[path] = offset + len(chunk.encode("utf-8", errors="replace"))
    # If the chunk doesn't end with newline, we shouldn't emit the trailing
    # partial line — but for simplicity we return all lines and trust that
    # JSONL writers flush whole records (they do in practice).
    return [ln for ln in chunk.splitlines() if ln.strip()]


async def _emit_for_changes(changed: Iterable[Path], hub: Hub) -> None:
    settings = get_settings()
    repo_paths = settings.repo_paths
    for path in changed:
        if path.suffix != ".jsonl" or not path.is_file():
            continue
        new_lines = _tail_new_lines(path)
        if not new_lines:
            continue
        # parse_jsonl re-reads the whole file; for incremental we can build
        # mini events ourselves.
        for raw in new_lines:
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ev = _line_to_event(obj, repo_paths)
            if ev is not None:
                await hub.broadcast(ev)


def _line_to_event(obj: dict, repo_paths: list[Path]) -> ParsedEvent | None:
    """Convert one JSONL record to a ParsedEvent, or None to skip."""
    from datetime import datetime

    t = obj.get("type", "")
    cwd = obj.get("cwd")
    repo = "unknown"
    for rp in repo_paths:
        try:
            if cwd and Path(cwd).is_relative_to(rp):
                repo = rp.name
                break
        except (TypeError, ValueError):
            continue
    raw_ts = obj.get("timestamp")
    ts = None
    if raw_ts:
        try:
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            ts = None
    if ts is None:
        return None

    if t == "user":
        text = ""
        msg = obj.get("message", {}) or {}
        c = msg.get("content", "")
        if isinstance(c, str):
            text = c
        if text.startswith("/"):
            return ParsedEvent(ts, repo, "command", {"cmd": text.split()[0], "msg": text[:140]})
        return None

    if t == "assistant":
        msg = obj.get("message", {}) or {}
        content = msg.get("content", [])
        if isinstance(content, list):
            for c in content:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                tool = c.get("name", "")
                ti = c.get("input", {}) or {}
                if tool == "Task":
                    return ParsedEvent(
                        ts,
                        repo,
                        "delegate",
                        {
                            "from": "main",
                            "to": str(ti.get("subagent_type") or ti.get("description", "")),
                            "msg": str(ti.get("prompt", ""))[:140],
                        },
                    )
                if tool == "Skill":
                    return ParsedEvent(
                        ts,
                        repo,
                        "skill",
                        {"skill": str(ti.get("skill") or ti.get("path") or "skill")},
                    )
                target = (
                    ti.get("file_path") or ti.get("path") or ti.get("command") or ti.get("pattern") or ""
                )
                return ParsedEvent(ts, repo, "tool", {"tool": tool, "target": str(target)[:200]})
    return None


async def _watch_loop(projects_dir: Path, hub: Hub) -> None:
    if not projects_dir.is_dir():
        logger.info("projects_dir missing, watcher idle: %s", projects_dir)
        # Keep the task alive so cancellation works cleanly.
        while True:
            await asyncio.sleep(60)

    # Seed offsets from current file sizes so we don't replay history.
    for f in projects_dir.rglob("*.jsonl"):
        try:
            _offsets[f] = f.stat().st_size
        except OSError:
            pass

    logger.info("live_stream watching %s (%d files seeded)", projects_dir, len(_offsets))
    try:
        async for change_set in watchfiles.awatch(
            projects_dir, recursive=True, stop_event=None, watch_filter=lambda _ch, p: p.endswith(".jsonl")
        ):
            paths = {Path(p) for _ch, p in change_set}
            await _emit_for_changes(paths, hub)
    except asyncio.CancelledError:
        logger.info("live_stream watcher cancelled")
        raise


async def start_watcher() -> Hub:
    settings = get_settings()
    hub = get_hub()
    if hub._task is None or hub._task.done():
        task = asyncio.create_task(_watch_loop(settings.projects_dir, hub))
        hub.attach_task(task)
    return hub


async def stop_watcher() -> None:
    hub = get_hub()
    await hub.stop()
