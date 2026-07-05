"""Diff endpoints — single-diff `recent` (with hunks) and `list` (metadata
across all tracked repos, derived from LiveEventRow tool events + git numstat)."""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

import app.db as db_mod
from app.config import get_settings
from app.models.session_event import LiveEventRow
from app.models.session_summary import SessionSummaryRow
from app.schemas.session import Diff, DiffHunk, DiffLine, RecentDiffItem

logger = logging.getLogger(__name__)
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
        logger.warning("git diff failed to run for %s/%s", repo, file_relative)
        return []
    if out.returncode != 0:
        logger.warning(
            "git diff exited %d for %s/%s: %s",
            out.returncode, repo, file_relative, out.stderr.strip(),
        )
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
        # Pull recent tool events; can't filter tool-name in SQL (JSON payload)
        # so we widen the pool and let the Python loop find the first Edit/
        # Write/MultiEdit. The session-active loop on a Bash-heavy day can
        # have 100+ Bash events with no Edit in the most recent 20.
        window_start = datetime.now(tz=UTC) - timedelta(hours=72)
        rows = (
            (
                await session.execute(
                    select(LiveEventRow)
                    .where(LiveEventRow.kind == "tool")
                    .where(LiveEventRow.ts >= window_start)
                    .order_by(LiveEventRow.ts.desc())
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
            # Translate host path (e.g. /Users/me/Documents/x) → container
            # path (/host/home/Documents/x) so .relative_to() can match the
            # registered repo paths. Bare-metal deployments no-op.
            translated = settings.translate_host_path(target)
            for repo_path in settings.repo_paths:
                try:
                    rel = str(translated.relative_to(repo_path))
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


@router.get("/diffs/file", response_model=Diff)
async def file_diff(
    repo: str = Query(..., description="Repo directory name (e.g. 'claude-tracker')"),
    path: str = Query(..., description="File path relative to repo root"),
) -> Diff:
    """Return the current uncommitted diff for a specific file.

    Used by the /diff page when clicking a row in the recent-diffs list to
    drill into a particular file. Looks up the repo by name (matching the
    registered repo_paths basename), runs `git diff --unified=2` for the
    given relative path, and joins SessionSummary for the most recent agent
    that edited the file (best-effort; may be empty).
    """
    settings = get_settings()
    repo_path = next((p for p in settings.repo_paths if p.name == repo), None)
    if repo_path is None:
        raise HTTPException(404, f"unknown repo: {repo}")
    hunks = _git_diff(repo_path, path)
    if not hunks:
        raise HTTPException(404, f"no current diff for {repo}/{path}")

    # Best-effort agent + session lookup: most-recent tool event on this file
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    agent = ""
    session_short = ""
    async with sm() as session:
        rows = (
            (
                await session.execute(
                    select(LiveEventRow)
                    .where(LiveEventRow.kind == "tool")
                    .order_by(LiveEventRow.ts.desc())
                    .limit(500)
                )
            )
            .scalars()
            .all()
        )
        for ev in rows:
            payload = json.loads(ev.payload) if ev.payload else {}
            target = payload.get("target", "")
            if not target:
                continue
            try:
                rel = str(settings.translate_host_path(target).relative_to(repo_path))
            except (ValueError, OSError):
                continue
            if rel != path:
                continue
            summary = await session.get(SessionSummaryRow, ev.session_id)
            agent = (summary.agent if summary else "") or ""
            session_short = ev.session_id[:8]
            break

    return Diff(file=path, agent=agent, session=session_short, hunks=hunks)


def _git_numstat(repo: Path, rel: str) -> tuple[int, int] | None:
    """Return (adds, dels) for the uncommitted change vs HEAD on `rel`.

    Returns None for binary files, git failures, or files with no current
    diff. Renames and deletions still produce valid integer counts. We use
    --numstat instead of parsing the full unified diff because the list
    endpoint only needs line counts; hunk content is the single-diff
    endpoint's job.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "diff", "--numstat", "HEAD", "--", rel],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("git numstat failed to run for %s/%s", repo, rel)
        return None
    if out.returncode != 0:
        logger.warning("git numstat exited %d for %s/%s: %s", out.returncode, repo, rel, out.stderr.strip())
        return None
    line = out.stdout.strip().split("\n", 1)[0] if out.stdout else ""
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 2 or parts[0] == "-":  # binary file -> "-\t-\t<path>"
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _find_git_ancestor(path: Path) -> Path | None:
    """Walk up from `path` and return the nearest ancestor containing .git.

    Used to discover the repo root for files in repos that aren't in the
    registered list — so e.g. carioca shows up on /diff without having to
    be added through the UI, as long as its host home is mounted.
    """
    try:
        cur = path if path.is_dir() else path.parent
        for _ in range(20):  # max depth — don't walk forever
            if (cur / ".git").is_dir():
                return cur
            if cur == cur.parent:
                return None
            cur = cur.parent
    except OSError:
        return None
    return None


def _git_status_porcelain(repo: Path) -> list[str]:
    """Return relative paths of files with uncommitted changes vs HEAD.

    Skips untracked files (we want to surface real edits, not noise from
    build artifacts). Renames return the new path; deletions still appear.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=no"],
            capture_output=True, text=True, timeout=4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("git status failed to run for %s", repo)
        return []
    if out.returncode != 0:
        logger.warning("git status exited %d for %s: %s", out.returncode, repo, out.stderr.strip())
        return []
    paths: list[str] = []
    for line in out.stdout.splitlines():
        # Format: "XY path" or "XY orig -> new" for renames.
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest)
    return paths


def _diff_items_for_repo(
    repo_name: str, repo_path: Path, window_start: datetime
) -> list[RecentDiffItem]:
    # Blocking per-repo work (git status + numstat + file stat) -- run via
    # asyncio.to_thread, one call per repo, gathered concurrently so N repos
    # do not serialize N subprocess round-trips on the event loop.
    items: list[RecentDiffItem] = []
    for rel in _git_status_porcelain(repo_path):
        stat = _git_numstat(repo_path, rel)
        if stat is None or stat == (0, 0):
            continue
        try:
            mtime = (repo_path / rel).stat().st_mtime
            ts = datetime.fromtimestamp(mtime, tz=UTC)
        except OSError:
            # File was deleted on disk (still in git status as `D`).
            # Fall back to now() so it sorts to the top -- recent
            # deletion is recent activity.
            ts = datetime.now(tz=UTC)
        if ts < window_start:
            continue
        items.append(RecentDiffItem(
            ts=ts, file=rel, repo=repo_name,
            adds=stat[0], dels=stat[1], agent="",
        ))
    return items


@router.get("/diffs/list", response_model=list[RecentDiffItem])
async def list_diffs() -> list[RecentDiffItem]:
    """Files with uncommitted changes across every repo Claude has touched.

    Pivots on `git status` per-repo rather than on Edit-tool events, so:
      - Edits applied via Bash (heredoc/sed/python script) show up too —
        the previous version only saw Edit/Write/MultiEdit tool calls and
        missed everything else.
      - Time column reflects the file's actual mtime on disk, not when an
        Edit tool was invoked (could be hours/days apart).
      - Repos discovered automatically by walking from event file paths to
        the nearest .git ancestor — even repos not in the registered list
        appear, as long as their host home is mounted into the container.
    """
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    settings = get_settings()
    window_start = datetime.now(tz=UTC) - timedelta(hours=72)

    # 1) Build the candidate repo set: registered paths + discovered ancestors
    #    from any tool event's target in the window.
    repo_paths_by_name: dict[str, Path] = {p.name: p for p in settings.repo_paths}

    async with sm() as session:
        events = (
            (
                await session.execute(
                    select(LiveEventRow)
                    .where(LiveEventRow.kind == "tool")
                    .where(LiveEventRow.ts >= window_start)
                    .order_by(LiveEventRow.ts.desc())
                )
            )
            .scalars()
            .all()
        )

    for ev in events:
        try:
            payload = json.loads(ev.payload) if ev.payload else {}
        except json.JSONDecodeError:
            continue
        target = payload.get("target", "")
        if not target:
            continue
        translated = settings.translate_host_path(target)
        anchor = _find_git_ancestor(translated)
        if anchor is None:
            continue
        repo_paths_by_name.setdefault(anchor.name, anchor)

    # 2) For each candidate repo, ask git what's currently changed and
    #    compose a RecentDiffItem per file (using file mtime as `ts`).
    #    Files whose mtime falls outside the window are dropped — they're
    #    stale uncommitted work (e.g. months-old PDFs git thinks changed),
    #    not "recent diffs" in any useful sense.
    results = await asyncio.gather(
        *(
            asyncio.to_thread(_diff_items_for_repo, repo_name, repo_path, window_start)
            for repo_name, repo_path in repo_paths_by_name.items()
        )
    )
    items: list[RecentDiffItem] = [item for repo_items in results for item in repo_items]

    items.sort(key=lambda x: x.ts, reverse=True)
    items = items[:30]

    # 3) Best-effort agent attribution: for the surviving (repo, file)
    #    pairs, find the most recent matching Edit event in the window
    #    and grab its session's agent. Skipped silently when no event
    #    matched (rows still render; agent shows blank).
    key_set = {(it.repo, it.file) for it in items}
    last_edit_by_key: dict[tuple[str, str], str] = {}
    for ev in events:
        try:
            payload = json.loads(ev.payload) if ev.payload else {}
        except json.JSONDecodeError:
            continue
        if payload.get("tool") not in ("Edit", "Write", "MultiEdit"):
            continue
        target = payload.get("target", "")
        if not target:
            continue
        translated = settings.translate_host_path(target)
        anchor = _find_git_ancestor(translated)
        if anchor is None:
            continue
        try:
            rel = str(translated.relative_to(anchor))
        except ValueError:
            continue
        key = (anchor.name, rel)
        if key in key_set and key not in last_edit_by_key:
            last_edit_by_key[key] = ev.session_id  # events already ordered desc

    if last_edit_by_key:
        async with sm() as session:
            agent_rows = (
                await session.execute(
                    select(SessionSummaryRow.session_id, SessionSummaryRow.agent)
                    .where(SessionSummaryRow.session_id.in_(set(last_edit_by_key.values())))
                )
            ).all()
        agent_by_sid = {sid: (agent or "") for sid, agent in agent_rows}
        for it in items:
            sid = last_edit_by_key.get((it.repo, it.file))
            if sid:
                it.agent = agent_by_sid.get(sid, "")

    return items
