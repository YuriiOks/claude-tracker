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
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import watchfiles

from app.config import get_settings
from app.services.jsonl_parser import ParsedEvent

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self, max_queue_per_client: int = 256) -> None:
        self._subs: list[asyncio.Queue[ParsedEvent]] = []
        self._max = max_queue_per_client
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        # Process-lifetime monotonic counter for WS wire ids. These intentionally
        # do NOT match DB primary keys (that would require a DB round-trip on the
        # broadcast hot path) — they only need to be unique+increasing per
        # connection lifetime so the frontend can detect gaps/reorders on /ws/live.
        self._seq = 0

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
            self._seq += 1
            event.seq = self._seq
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
# Ingest signal -- lets the background ingest task (app.main._ingest_loop)
# react to a JSONL change within ~1-2s instead of waiting for its periodic
# safety-sweep interval. Purely in-memory / best-effort and independent of
# this module's own `_offsets` tailer above: this queue only carries WHICH
# paths changed so ingest.py's persisted per-file cursors (ingest_file_state)
# can be advanced -- it doesn't carry parsed content. Unbounded: a burst is
# naturally capped by however many files watchfiles reports in one
# change_set, and Path objects are tiny.
# ---------------------------------------------------------------------------
_ingest_signal_queue: asyncio.Queue[Path] = asyncio.Queue()


def get_ingest_signal_queue() -> asyncio.Queue[Path]:
    return _ingest_signal_queue


# ---------------------------------------------------------------------------
# Tailer
# ---------------------------------------------------------------------------

# We avoid re-parsing each file from scratch on every change by tracking byte
# offsets. Each tail call returns the events emitted by the new bytes.

_offsets: dict[Path, int] = defaultdict(int)

# Last-seen `agentName` (from a "agent-name" JSONL record) per tailed file —
# mirrors jsonl_parser.parse_jsonl's per-file `agent_name` local, which is
# used as the delegate "from" for the persisted path. The live tailer reads
# a file incrementally across multiple watcher ticks, so this has to be kept
# across calls instead of as a loop-local.
_agent_names: dict[Path, str] = {}


def _tail_new_lines(path: Path) -> list[str]:
    """Read any unread bytes from path; return complete lines.

    Only advances the byte offset up to the last complete newline. A
    trailing partial line (e.g. a concurrent writer mid-flush) is left
    unread so it gets re-read whole on the next tick instead of being
    parsed as JSON and dropped.
    """
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
        with path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
    except OSError:
        return []
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        # No complete line yet; leave the offset untouched.
        return []
    complete, _partial = chunk[: last_nl + 1], chunk[last_nl + 1 :]
    _offsets[path] = offset + last_nl + 1
    text = complete.decode("utf-8", errors="replace")
    return [ln for ln in text.splitlines() if ln.strip()]


async def _emit_for_changes(changed: Iterable[Path], hub: Hub) -> None:
    from app.services.live_agents import get_tracker

    settings = get_settings()
    repo_paths = settings.repo_paths
    tracker = get_tracker()
    for path in changed:
        if path.suffix != ".jsonl" or not path.is_file():
            continue
        new_lines = _tail_new_lines(path)
        if not new_lines:
            continue
        for raw in new_lines:
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "agent-name":
                name = obj.get("agentName")
                if name:
                    _agent_names[path] = name
                continue
            ev = _line_to_event(obj, repo_paths, agent_name=_agent_names.get(path))
            if ev is not None:
                session_id = obj.get("sessionId")
                if session_id:
                    ev.payload["sessionId"] = session_id
                # Update active-agent map AND broadcast to WS subscribers.
                await tracker.record(
                    session_id=obj.get("sessionId"),
                    repo=ev.repo,
                    kind=ev.kind,
                    payload=ev.payload,
                    ts=ev.ts,
                )
                await hub.broadcast(ev)


def _line_to_event(
    obj: dict, repo_paths: list[Path], agent_name: str | None = None
) -> ParsedEvent | None:
    """Convert one JSONL record to a ParsedEvent, or None to skip."""
    from datetime import datetime

    t = obj.get("type", "")
    cwd = obj.get("cwd")
    from app.services.jsonl_parser import _repo_from_cwd
    repo = _repo_from_cwd(cwd, repo_paths)
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
                            "from": agent_name or "main",
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


# A crashed `watchfiles.awatch` iteration (e.g. an OSError bubbling up from
# the underlying inotify/FSEvents backend) restarts after this many seconds,
# doubling on each consecutive failure up to the cap below -- short enough to
# recover quickly from a transient hiccup, capped so a persistent problem
# doesn't spin the loop hot. Module-level so tests can shrink it.
_WATCH_RESTART_BACKOFF_INITIAL_SEC = 2.0
_WATCH_RESTART_BACKOFF_MAX_SEC = 30.0


async def _watch_loop(projects_dir: Path, hub: Hub) -> None:
    while not projects_dir.is_dir():  # noqa: ASYNC240
        logger.info("projects_dir missing, watcher idle: %s", projects_dir)
        await asyncio.sleep(60)

    # Seed offsets from current file sizes so we don't replay history.
    for f in projects_dir.rglob("*.jsonl"):  # noqa: ASYNC240
        try:
            _offsets[f] = f.stat().st_size  # noqa: ASYNC240
        except OSError:
            pass

    logger.info("live_stream watching %s (%d files seeded)", projects_dir, len(_offsets))

    # Only asyncio.CancelledError (deliberate shutdown, via Hub.stop()) may
    # propagate out of this loop. Any other exception out of watchfiles.awatch
    # -- an OSError from the underlying inotify/FSEvents backend is the
    # common one -- must not kill the watcher for good: log a warning and
    # restart the watch after a short, exponentially-capped backoff instead.
    backoff = _WATCH_RESTART_BACKOFF_INITIAL_SEC
    while True:
        try:
            async for change_set in watchfiles.awatch(
                projects_dir,
                recursive=True,
                stop_event=None,
                watch_filter=lambda _ch, p: p.endswith(".jsonl"),
                # watchfiles' defaults (debounce=1600ms, step=50ms) cap worst-case
                # live-feed latency at ~1.6s. Both args are milliseconds; tighten
                # them so /ws/live reflects new JSONL lines within ~250ms.
                debounce=250,
                step=25,
            ):
                backoff = _WATCH_RESTART_BACKOFF_INITIAL_SEC  # a healthy tick resets the backoff
                paths = {Path(p) for _ch, p in change_set}
                signal_queue = get_ingest_signal_queue()
                for p in paths:
                    signal_queue.put_nowait(p)
                await _emit_for_changes(paths, hub)
            return  # awatch's generator ended on its own -- nothing left to watch
        except asyncio.CancelledError:
            logger.info("live_stream watcher cancelled")
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("live_stream watcher crashed, restarting in %.1fs: %s", backoff, e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _WATCH_RESTART_BACKOFF_MAX_SEC)


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
