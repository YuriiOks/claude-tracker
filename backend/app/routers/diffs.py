"""GET /api/diffs/recent — last Edit/Write event paired with `git diff`."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import select

import app.db as db_mod
from app.config import get_settings
from app.models.session_event import LiveEventRow
from app.models.session_summary import SessionSummaryRow
from app.schemas.session import Diff, DiffHunk, DiffLine

router = APIRouter(tags=["diffs"])


def _git_diff(repo: Path, file_relative: str) -> list[DiffHunk]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "diff", "--unified=2", "--", file_relative],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    for line in out.stdout.splitlines():
        if line.startswith("@@"):
            current = DiffHunk(header=line, lines=[])
            hunks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current.lines.append(DiffLine(type="add", text=line[1:]))
        elif line.startswith("-") and not line.startswith("---"):
            current.lines.append(DiffLine(type="del", text=line[1:]))
        elif line.startswith(" "):
            current.lines.append(DiffLine(type="ctx", text=line[1:]))
    return hunks


@router.get("/diffs/recent")
async def recent_diff() -> Diff | None:
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    settings = get_settings()
    async with sm() as session:
        rows = (
            (
                await session.execute(
                    select(LiveEventRow)
                    .where(LiveEventRow.kind == "tool")
                    .order_by(LiveEventRow.ts.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        for ev in rows:
            payload = json.loads(ev.payload) if ev.payload else {}
            tool = payload.get("tool", "")
            target = payload.get("target", "")
            if tool not in ("Edit", "Write", "MultiEdit") or not target:
                continue
            for repo_path in settings.repo_paths:
                try:
                    rel = str(Path(target).relative_to(repo_path))
                except (ValueError, OSError):
                    continue
                hunks = _git_diff(repo_path, rel)
                if not hunks:
                    continue
                summary = await session.get(SessionSummaryRow, ev.session_id)
                return Diff(
                    file=rel,
                    agent=(summary.agent if summary else "") or "",
                    session=ev.session_id[:8],
                    hunks=hunks,
                )
    return None
