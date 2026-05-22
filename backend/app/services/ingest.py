"""Ingest JSONL files into SQLite. Idempotent — keyed on file mtime."""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import _ensure_engine, init_db  # noqa: PLC2701
from app.models.session_event import LiveEventRow
from app.models.session_summary import SessionSummaryRow
from app.services.jsonl_parser import iter_jsonl_files, parse_jsonl

logger = logging.getLogger(__name__)


async def ingest_all(since_hours: int | None = None, rebuild: bool = False) -> dict:
    """Walk projects_dir, parse new/modified JSONL files, upsert rows."""
    await init_db()
    from app.db import _sessionmaker

    settings = get_settings()
    repo_paths = settings.repo_paths
    cutoff = None
    if since_hours is not None:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=since_hours)

    new_count = 0
    updated_count = 0
    skipped = 0
    event_count = 0
    started = time.perf_counter()

    if _sessionmaker is None:
        raise RuntimeError("DB sessionmaker not initialized — call await init_db() first")
    async with _sessionmaker() as session:  # type: AsyncSession
        if rebuild:
            await session.execute(delete(LiveEventRow))
            await session.execute(delete(SessionSummaryRow))
            await session.commit()

        for path in iter_jsonl_files(settings.projects_dir):
            try:
                stat = path.stat()
            except OSError:
                continue
            if cutoff and datetime.fromtimestamp(stat.st_mtime, tz=UTC) < cutoff:
                skipped += 1
                continue

            summary, events = parse_jsonl(path, repo_paths)
            if summary is None:
                continue

            # Mark running if file was modified within last 60 seconds.
            now_ts = time.time()
            if now_ts - stat.st_mtime < 60:
                summary.status = "running"

            # Look up by the session_id extracted from JSONL content (not the filename
            # stem) so that continuation/agent files sharing a parent session_id
            # correctly find the existing row instead of triggering a UNIQUE violation.
            existing = await session.get(SessionSummaryRow, summary.session_id)
            if existing and not rebuild and abs(existing.file_mtime - stat.st_mtime) < 0.5:
                skipped += 1
                continue

            if existing:
                existing.repo = summary.repo
                existing.started_at = summary.started_at
                existing.last_event_at = summary.last_event_at
                existing.agent = summary.agent
                existing.task = summary.task
                existing.status = summary.status
                existing.tokens = summary.tokens
                existing.cost = summary.cost
                existing.edits = summary.edits
                existing.file_path = summary.file_path
                existing.file_mtime = summary.file_mtime
                # Drop old events for this session and re-insert.
                await session.execute(
                    delete(LiveEventRow).where(LiveEventRow.session_id == summary.session_id)
                )
                updated_count += 1
            else:
                row = SessionSummaryRow(
                    session_id=summary.session_id,
                    repo=summary.repo,
                    started_at=summary.started_at,
                    last_event_at=summary.last_event_at,
                    agent=summary.agent,
                    task=summary.task,
                    status=summary.status,
                    tokens=summary.tokens,
                    cost=summary.cost,
                    edits=summary.edits,
                    file_path=summary.file_path,
                    file_mtime=summary.file_mtime,
                )
                session.add(row)
                new_count += 1

            for ev in events:
                session.add(
                    LiveEventRow(
                        session_id=summary.session_id,
                        repo=summary.repo,
                        ts=ev.ts,
                        kind=ev.kind,
                        payload=json.dumps(ev.payload),
                    )
                )
                event_count += 1

            await session.commit()

    return {
        "new": new_count,
        "updated": updated_count,
        "skipped": skipped,
        "events": event_count,
        "elapsed_s": round(time.perf_counter() - started, 2),
    }


async def fetch_recent_summaries(repo: str | None = None, limit: int = 50) -> list[SessionSummaryRow]:
    _ensure_engine()
    from app.db import _sessionmaker

    if _sessionmaker is None:
        raise RuntimeError('DB sessionmaker not initialized — call await init_db() first')
    async with _sessionmaker() as session:
        stmt = select(SessionSummaryRow).order_by(SessionSummaryRow.last_event_at.desc()).limit(limit)
        if repo:
            stmt = stmt.where(SessionSummaryRow.repo == repo)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def fetch_recent_events(limit: int = 60, repo: str | None = None) -> list[LiveEventRow]:
    _ensure_engine()
    from app.db import _sessionmaker

    if _sessionmaker is None:
        raise RuntimeError('DB sessionmaker not initialized — call await init_db() first')
    async with _sessionmaker() as session:
        stmt = select(LiveEventRow).order_by(LiveEventRow.ts.desc()).limit(limit)
        if repo:
            stmt = select(LiveEventRow).where(LiveEventRow.repo == repo).order_by(LiveEventRow.ts.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(reversed(list(result.scalars().all())))
