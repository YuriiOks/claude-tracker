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
from app.models.session_hour import SessionHourRow
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow
from app.services.jsonl_parser import iter_jsonl_files, parse_jsonl

logger = logging.getLogger(__name__)

# Internal Claude Code system files stored in subagents/ that are NOT user-invoked
# Task() calls: context compaction, inline prompt suggestions, side questions, etc.
# Filename pattern: agent-a{type}-{hex}.jsonl where type is one of these prefixes.
_INTERNAL_SUBAGENT_PREFIXES = ("acompact-", "aprompt_suggestion-", "aside_question-")


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
            await session.execute(delete(SessionHourRow))
            await session.execute(delete(SubagentCallRow))
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

            # ---- Subagent file: route to SubagentCallRow, skip session_summary ----
            if path.parent.name == "subagents":
                # Skip Claude Code internal system files (compaction, prompt suggestions, etc.).
                # These live in subagents/ but are not user-initiated Task() invocations.
                _stem_id = path.stem[len("agent-"):]  # strip "agent-" prefix -> agentId
                if any(_stem_id.startswith(p) for p in _INTERNAL_SUBAGENT_PREFIXES):
                    skipped += 1
                    continue
                meta_path = path.with_suffix("").with_suffix(".meta.json")
                agent_type = summary.agent or "unknown"
                try:
                    meta = json.loads(meta_path.read_text())
                    agent_type = meta.get("agentType") or agent_type
                except Exception:  # noqa: BLE001
                    pass
                existing_sc = (await session.execute(
                    select(SubagentCallRow).where(SubagentCallRow.file_path == str(path))
                )).scalar_one_or_none()
                if existing_sc and not rebuild and abs(existing_sc.file_mtime - stat.st_mtime) < 0.5:
                    skipped += 1
                    continue
                if existing_sc:
                    existing_sc.agent_type = agent_type
                    existing_sc.tokens = summary.tokens
                    existing_sc.cost = summary.cost
                    existing_sc.file_mtime = summary.file_mtime
                else:
                    session.add(SubagentCallRow(
                        session_id=summary.session_id,
                        agent_type=agent_type,
                        repo=summary.repo,
                        tokens=summary.tokens,
                        cost=summary.cost,
                        started_at=summary.started_at,
                        file_path=str(path),
                        file_mtime=summary.file_mtime,
                    ))
                    new_count += 1
                await session.commit()
                continue  # skip normal session_summary path

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

            content_win: bool
            if existing:
                # Prefer the richer file — subagent files share the session_id but
                # have far fewer tokens than the main JSONL. Only overwrite content
                # fields when this file has at least as many tokens as what's stored.
                content_win = summary.tokens >= existing.tokens
                # RISK: if Claude Code resumes a session into a new JSONL file
                # whose token count has not yet caught up to the prior file (e.g.
                # right after a resume, before much new content has been written),
                # this merge can pick the WRONG file as the content source and
                # silently drop that session's LiveEvents (they get deleted below
                # and never re-inserted from the losing file). Not rewriting this
                # merge here -- flagging for a dedicated fixture test.
                # TODO(test): pin merge semantics for same-sessionId file races.
                if content_win:
                    existing.repo = summary.repo
                    existing.started_at = summary.started_at
                    existing.agent = summary.agent
                    existing.task = summary.task
                    existing.tokens = summary.tokens
                    existing.cost = summary.cost
                    existing.edits = summary.edits
                    existing.file_path = summary.file_path
                    # Drop old events for this session and re-insert.
                    await session.execute(
                        delete(LiveEventRow).where(LiveEventRow.session_id == summary.session_id)
                    )
                # Always update recency + status so live sessions stay current.
                # SQLite stores naive datetimes; summary timestamps are UTC-aware.
                _existing_ts = existing.last_event_at
                if _existing_ts.tzinfo is None:
                    _existing_ts = _existing_ts.replace(tzinfo=UTC)
                if summary.last_event_at > _existing_ts:
                    existing.last_event_at = summary.last_event_at
                existing.status = summary.status
                existing.file_mtime = summary.file_mtime
                updated_count += 1
            else:
                content_win = True
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

            # Upsert per-hour token buckets — only touch hours this file contributes.
            # Do NOT delete all hours for the session: that would erase data from the
            # main JSONL when a smaller subagent file processes afterwards.
            hourly = getattr(summary, "hourly_tokens", {}) or {}
            if hourly:
                await session.execute(
                    delete(SessionHourRow).where(
                        SessionHourRow.session_id == summary.session_id,
                        SessionHourRow.hour_ts.in_(list(hourly.keys())),
                    )
                )
                for hour_ts, tok in hourly.items():
                    session.add(
                        SessionHourRow(
                            session_id=summary.session_id,
                            repo=summary.repo,
                            hour_ts=hour_ts,
                            tokens=tok,
                        )
                    )

            if content_win:
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
