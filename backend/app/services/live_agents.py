"""In-memory 'currently active' map fed by the live JSONL tailer.

For each session_id we remember: the active agent (last delegate target or
'main'), the last tool + target, the started/last-seen timestamps. The map
prunes entries older than `STALE_SECONDS` so the API only ever returns
sessions Claude Code is actually still working on.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

STALE_SECONDS = 60


@dataclass
class _Activity:
    session_id: str
    repo: str
    agent: str = "main"
    current_tool: str | None = None
    current_target: str | None = None
    task: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class _Tracker:
    def __init__(self) -> None:
        self._sessions: dict[str, _Activity] = {}
        self._lock = asyncio.Lock()

    async def record(
        self,
        session_id: str | None,
        repo: str,
        kind: str,
        payload: dict[str, Any],
        ts: datetime | None = None,
    ) -> None:
        if not session_id:
            return
        ts = ts or datetime.now(tz=UTC)
        async with self._lock:
            act = self._sessions.get(session_id)
            if act is None:
                act = _Activity(session_id=session_id, repo=repo, started_at=ts)
                self._sessions[session_id] = act
            act.last_seen_at = ts
            act.repo = repo or act.repo
            if kind == "delegate":
                target = payload.get("to") or ""
                if target:
                    act.agent = target
            elif kind == "agent_start":
                target = payload.get("agent") or ""
                if target:
                    act.agent = target
            elif kind == "tool":
                act.current_tool = payload.get("tool")
                act.current_target = payload.get("target")
            elif kind == "command":
                act.current_tool = payload.get("cmd")
                act.current_target = None

    async def snapshot(self) -> list[dict[str, Any]]:
        now = datetime.now(tz=UTC)
        cutoff = now - timedelta(seconds=STALE_SECONDS)
        async with self._lock:
            stale = [sid for sid, a in self._sessions.items() if a.last_seen_at < cutoff]
            for sid in stale:
                self._sessions.pop(sid, None)
            out = []
            for a in self._sessions.values():
                out.append(
                    {
                        "sessionId": a.session_id[:8],
                        "repo": a.repo,
                        "agent": a.agent,
                        "currentTool": a.current_tool,
                        "currentTarget": a.current_target,
                        "task": a.task,
                        "startedAt": a.started_at.isoformat(),
                        "lastSeenAt": a.last_seen_at.isoformat(),
                        "elapsedSec": int((now - a.started_at).total_seconds()),
                        "secondsSinceLastEvent": int((now - a.last_seen_at).total_seconds()),
                    }
                )
            out.sort(key=lambda x: x["secondsSinceLastEvent"])
            return out

    async def reset(self) -> None:  # for tests
        async with self._lock:
            self._sessions.clear()


_tracker: _Tracker | None = None


def get_tracker() -> _Tracker:
    global _tracker
    if _tracker is None:
        _tracker = _Tracker()
    return _tracker
