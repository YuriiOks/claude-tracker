"""Ingest JSONL files into SQLite. Idempotent — keyed on file mtime."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _ensure_engine, init_db  # noqa: PLC2701
from app.models.ingest_meta import SINGLETON_ID, IngestMetaRow
from app.models.message_ledger import MessageLedgerRow
from app.models.session_event import LiveEventRow
from app.models.session_hour import SessionHourRow
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow
from app.services.jsonl_parser import SessionSummary, iter_jsonl_files, parse_jsonl

logger = logging.getLogger(__name__)

# Bump whenever the JSONL -> SQL derivation rules change in a way that makes
# already-ingested rows wrong (e.g. the workflow-agent routing fix below).
# ingest_all() compares this against app.models.ingest_meta.IngestMetaRow and
# does a one-time full rebuild of the JSONL-derived tables when it's behind.
INGEST_VERSION = 2

# Internal Claude Code system files stored in subagents/ that are NOT user-invoked
# Task() calls: context compaction, inline prompt suggestions, side questions, etc.
# Filename pattern: agent-a{type}-{hex}.jsonl where type is one of these prefixes.
_INTERNAL_SUBAGENT_PREFIXES = ("acompact-", "aprompt_suggestion-", "aside_question-")

# Prefix marking a SessionHourRow.session_id as a synthetic bucket for
# subagent/workflow-agent token totals rather than a real session_id. Used so
# heatmap_stats() can sum these rows into tokenGrid/repoTokens48h (spend is
# spend, wherever it came from) while excluding them from the plain
# session-activity grid/repo48h counts (a subagent call is not "a session").
SUBAGENT_HOUR_PREFIX = "sub:"


def _subagent_hour_key(path: Path) -> str:
    """Deterministic, collision-safe SessionHourRow.session_id for a subagent
    file's own hourly buckets. Keying off a hash of the absolute file path
    (rather than the parent session_id) keeps it stable across re-ingest
    (idempotent upsert) and guarantees it never collides with the real
    parent session's own session_hour rows -- sharing the real session_id
    would either violate the (session_id, hour_ts) unique index or silently
    overwrite whichever file processed that hour last instead of summing.
    """
    digest = hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:20]
    return f"{SUBAGENT_HOUR_PREFIX}{digest}"


async def _read_ingest_version(session: AsyncSession) -> int | None:
    """Return the stored ingest logic version, or None if no row exists yet
    (a brand-new DB, or an existing DB from before this table existed).

    Read-only -- never writes the marker. The caller must persist the new
    version via `_mark_ingest_version` only AFTER a full rebuild walk has
    completed without raising (see ingest_all()). Writing it any earlier
    would tell the next startup the DB is already healed when a mid-rebuild
    crash (plausible on a multi-GB / thousands-of-files corpus) actually
    left it only partially rebuilt.
    """
    row = await session.get(IngestMetaRow, SINGLETON_ID)
    return row.version if row is not None else None


async def _mark_ingest_version(session: AsyncSession, version: int) -> None:
    """Persist the ingest logic version. Must only be called as the LAST
    step of a full rebuild walk that has already completed without raising
    -- see _read_ingest_version and ingest_all().
    """
    row = await session.get(IngestMetaRow, SINGLETON_ID)
    if row is None:
        session.add(IngestMetaRow(id=SINGLETON_ID, version=version))
    else:
        row.version = version
    await session.commit()


# SQLITE_MAX_VARIABLE_NUMBER defaults to 999 on older SQLite builds (some
# ship even lower) -- a single long-running session or a big subagent
# transcript can carry thousands of message ids, so the ledger lookup below
# chunks its IN(...) clause instead of sending every id in one query.
_LEDGER_LOOKUP_CHUNK = 500


async def _reconcile_message_ledger(
    session: AsyncSession, summary: SessionSummary, file_path: str
) -> None:
    """Subtract any assistant message this file did NOT originate from
    summary.tokens/cost/hourly_tokens, in place, and claim ownership of any
    message id seen here for the first time.

    Claude Code can write the same message.id into more than one file: a
    resumed session copies forward earlier turns into a new top-level file,
    and (rarely) a broadcast system message lands identically in several
    concurrently-open sessions. "First file to claim a message id owns it"
    keeps every message counted exactly once across the whole corpus,
    including between a session's own main/continuation files and its
    subagent/workflow-agent files (this function is called from both
    ingest branches against the SAME global ledger).

    A file re-parsing itself (mtime changed, still growing) always owns its
    own previously-claimed ids, so incremental re-ingest of a single growing
    file stays additive and idempotent.
    """
    usage: dict = getattr(summary, "message_usage", None) or {}
    if not usage:
        return

    msg_ids = list(usage.keys())
    owner_by_id: dict[str, MessageLedgerRow] = {}
    for i in range(0, len(msg_ids), _LEDGER_LOOKUP_CHUNK):
        chunk = msg_ids[i:i + _LEDGER_LOOKUP_CHUNK]
        rows = (await session.execute(
            select(MessageLedgerRow).where(MessageLedgerRow.message_id.in_(chunk))
        )).scalars().all()
        owner_by_id.update({row.message_id: row for row in rows})

    for msg_id, (turn_tokens, turn_cost, hour_key) in usage.items():
        owner = owner_by_id.get(msg_id)
        if owner is None:
            session.add(
                MessageLedgerRow(message_id=msg_id, file_path=file_path, tokens=turn_tokens)
            )
            continue
        if owner.file_path == file_path:
            continue  # this file already owns it -- already counted above
        if not Path(owner.file_path).exists():
            # The previous owner's file was deleted or moved (rotation,
            # pruning) -- reclaim ownership for the current file instead of
            # subtracting this id to zero forever. Existence is only
            # checked for CONTESTED ids (owner present and different from
            # this file), so this stays cheap even on a large corpus.
            owner.file_path = file_path
            owner.tokens = turn_tokens
            continue
        # Claimed by a different, still-existing file -- drop this file's copy.
        summary.tokens -= turn_tokens
        summary.cost = round(summary.cost - turn_cost, 4)
        if hour_key is not None:
            remaining = summary.hourly_tokens.get(hour_key, 0) - turn_tokens
            if remaining > 0:
                summary.hourly_tokens[hour_key] = remaining
            else:
                summary.hourly_tokens.pop(hour_key, None)


async def _upsert_hourly(
    session: AsyncSession, hour_key_id: str, repo: str, hourly: dict
) -> None:
    """Upsert per-hour token buckets for one SessionHourRow "owner" key
    (a real session_id, or a synthetic subagent key from _subagent_hour_key).
    Only touches the exact hour keys this file contributes -- never deletes
    the owner's other hours, so a smaller file processed after a bigger one
    can't erase data the bigger file already wrote for a different hour.
    """
    if not hourly:
        return
    await session.execute(
        delete(SessionHourRow).where(
            SessionHourRow.session_id == hour_key_id,
            SessionHourRow.hour_ts.in_(list(hourly.keys())),
        )
    )
    for hour_ts, tok in hourly.items():
        if tok <= 0:
            continue
        session.add(SessionHourRow(session_id=hour_key_id, repo=repo, hour_ts=hour_ts, tokens=tok))


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
        stored_version = await _read_ingest_version(session)
        version_rebuild = stored_version is None or stored_version < INGEST_VERSION
        if version_rebuild:
            # A version-triggered rebuild must walk the FULL corpus, not just
            # whatever `since_hours` window the caller asked for -- we're
            # about to wipe everything below. The version marker itself is
            # only written at the very end of this function, after the walk
            # completes without raising -- see the `if version_rebuild:`
            # block below the for-loop. A crash mid-rebuild (plausible on a
            # multi-GB / thousands-of-files corpus) must leave the marker
            # stale/missing so the NEXT ingest_all() call detects it and
            # rebuilds again, instead of believing a half-finished DB is
            # already healed.
            rebuild = True
            cutoff = None
            logger.info("ingest logic version changed -> rebuilding JSONL-derived tables")

        if rebuild:
            # JSONL-derived tables ONLY -- never otel_event/otel_metric (a
            # separate OTLP-fed pipeline) and never the repo registry (a JSON
            # file, not a DB table at all).
            await session.execute(delete(LiveEventRow))
            await session.execute(delete(SessionSummaryRow))
            await session.execute(delete(SessionHourRow))
            await session.execute(delete(SubagentCallRow))
            await session.execute(delete(MessageLedgerRow))
            await session.commit()

        # Stat once per file and apply the cutoff filter BEFORE sorting -- a
        # since_hours-scoped tick would otherwise stat() and sort every file
        # in the whole corpus just to compute a sort key for files it's
        # about to skip anyway. The mtime captured here is reused below
        # instead of statting each surviving file a second time.
        candidates: list[tuple[Path, float]] = []
        for path in iter_jsonl_files(settings.projects_dir):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if cutoff and datetime.fromtimestamp(mtime, tz=UTC) < cutoff:
                skipped += 1
                continue
            candidates.append((path, mtime))

        # Oldest-first so that when two files share an assistant message.id
        # (a resumed session copying forward earlier turns into a new file),
        # the chronologically-original file is the one that claims it in
        # message_ledger and the newer copy is the one that gets deduped —
        # otherwise ownership on a full rebuild would depend on directory
        # walk order, which is arbitrary.
        for path, mtime in sorted(candidates, key=lambda item: item[1]):
            summary, events = parse_jsonl(path, repo_paths)
            if summary is None:
                continue

            # ---- Subagent-tree file: route to SubagentCallRow, skip session_summary ----
            # Matches BOTH direct Task() subagents (agent-*.jsonl directly under
            # subagents/) and workflow agents nested under
            # subagents/workflows/wf_x/agent-*.jsonl -- both kinds embed the
            # PARENT session's real session_id in their own JSONL content
            # (confirmed against real transcripts), so checking only
            # `path.parent.name == "subagents"` missed every workflow-agent
            # file: they fell through to the session_summary branch below,
            # shared session_id with the main file, and the "prefer the
            # richer file" merge kept only ONE file's tokens instead of
            # summing all of them (workflow runs can spawn 100+ agent files
            # per session -- this was the dominant source of the undercount).
            if "subagents" in path.parts:
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
                if existing_sc and not rebuild and abs(existing_sc.file_mtime - mtime) < 0.5:
                    skipped += 1
                    continue

                # Cross-file dedup against the SAME global ledger the
                # session_summary branch uses below -- a message the parent
                # session (or another subagent file) already claimed must
                # not also inflate this call's totals.
                await _reconcile_message_ledger(session, summary, str(path))

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

                await _upsert_hourly(
                    session, _subagent_hour_key(path), summary.repo, summary.hourly_tokens
                )

                await session.commit()
                continue  # skip normal session_summary path

            # Mark running if file was modified within last 60 seconds.
            now_ts = time.time()
            if now_ts - mtime < 60:
                summary.status = "running"

            # Look up by the session_id extracted from JSONL content (not the
            # filename stem) so that a resumed-in-place session (same file,
            # growing over time) correctly finds the existing row instead of
            # triggering a UNIQUE violation. Note: since the subagents-tree
            # routing fix above, files that legitimately share a session_id
            # with an existing row are, in practice, always the SAME file
            # reprocessed after it grew -- not a different file racing it.
            existing = await session.get(SessionSummaryRow, summary.session_id)
            if existing and not rebuild and abs(existing.file_mtime - mtime) < 0.5:
                skipped += 1
                continue

            # Cross-file dedup: a resumed session can copy earlier turns into
            # a new top-level file under a NEW session_id, so this cannot be
            # caught by the SessionSummaryRow primary-key lookup above (that
            # only merges files that share the exact same session_id, which
            # main + its own continuations always do). Must run before the
            # existing/new branch below so summary.tokens already reflects
            # the deduped total when it's written. Runs after the skip check
            # (like the subagent branch above) so an unchanged file costs
            # nothing beyond the mtime comparison.
            await _reconcile_message_ledger(session, summary, str(path))

            content_win: bool
            if existing:
                # Prefer the richer file — belt-and-suspenders for any other
                # same-session_id race we haven't seen in practice. Only
                # overwrite content fields when this file has at least as
                # many tokens as what's stored.
                content_win = summary.tokens >= existing.tokens
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
            await _upsert_hourly(session, summary.session_id, summary.repo, summary.hourly_tokens)

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

        if version_rebuild:
            # Reached ONLY if the full walk above finished without raising
            # -- an exception anywhere in the loop propagates straight out
            # of this `async with` block, skipping this line, so the marker
            # stays stale/missing and the next ingest_all() call rebuilds
            # again from scratch. Marks the DB as healed for INGEST_VERSION
            # exactly once.
            await _mark_ingest_version(session, INGEST_VERSION)

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


async def fetch_subagent_totals(session_ids: list[str]) -> dict[str, tuple[int, float]]:
    """Sum SubagentCallRow tokens/cost per session_id, for the given ids.

    Used to fold a session's direct + workflow subagent spend into its own
    tokens/cost total wherever a single session is displayed (e.g.
    /api/sessions) -- a subagent call is not its own session, its spend
    belongs to whichever session spawned it.
    """
    if not session_ids:
        return {}
    _ensure_engine()
    from app.db import _sessionmaker

    if _sessionmaker is None:
        raise RuntimeError('DB sessionmaker not initialized — call await init_db() first')
    async with _sessionmaker() as session:
        rows = (await session.execute(
            select(
                SubagentCallRow.session_id,
                func.coalesce(func.sum(SubagentCallRow.tokens), 0),
                func.coalesce(func.sum(SubagentCallRow.cost), 0.0),
            )
            .where(SubagentCallRow.session_id.in_(session_ids))
            .group_by(SubagentCallRow.session_id)
        )).all()
    return {sid: (int(tok or 0), float(cost_v or 0.0)) for sid, tok, cost_v in rows}


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
