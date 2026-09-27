"""Ingest JSONL files into SQLite. Idempotent -- keyed on file mtime/size.

Per-file incremental cursors (byte offset, size, mtime, inode -- see
app.models.ingest_file_state.IngestFileStateRow) let a tick tell three cases
apart BEFORE opening a file:
  * unchanged (mtime+size match the stored cursor)      -> skip, zero I/O
  * grew (size > stored byte_offset, same inode)         -> parse only the
    appended bytes and merge the delta additively
  * shrank or was replaced (size < byte_offset, or the   -> full reparse that
    inode changed) or has no cursor yet (new file)          REPLACES this
                                                              file's prior
                                                              contribution
See `_ingest_one_file` for the decision tree.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _ensure_engine, init_db  # noqa: PLC2701
from app.models.ingest_file_state import IngestFileStateRow
from app.models.ingest_meta import SINGLETON_ID, IngestMetaRow
from app.models.message_ledger import MessageLedgerRow
from app.models.session_event import LiveEventRow
from app.models.session_hour import SessionHourRow
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow
from app.services.jsonl_parser import (
    SessionSummary,
    iter_jsonl_files,
    parse_jsonl_incremental,
)

logger = logging.getLogger(__name__)

# Bump whenever the JSONL -> SQL derivation rules change in a way that makes
# already-ingested rows wrong (e.g. the workflow-agent routing fix below), OR
# the on-disk cursor format changes shape.
# ingest_all() compares this against app.models.ingest_meta.IngestMetaRow and
# does a one-time full rebuild of the JSONL-derived tables when it's behind.
# v3: cost now bills cache_read_input_tokens (at a model-specific fraction of
# input price) and splits cache-write billing by TTL tier
# (ephemeral_1h/ephemeral_5m) instead of a flat 1.25x -- see
# jsonl_parser.py's _PRICING table and the cost formula in parse_jsonl().
# v4: true incremental parsing -- per-file byte offsets are now persisted in
# ingest_file_state instead of re-parsing every file whose mtime falls
# inside the sweep window on every tick. Bumped so every existing DB does
# exactly one full walk to establish cursors (offset = each file's current
# size) before incremental parsing takes over.
INGEST_VERSION = 4

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
# transcript can carry thousands of message ids, so any IN(...) lookup below
# chunks instead of sending every id/path in one query.
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
    subagent/workflow-agent files (this function is called from both the
    full-parse and incremental-delta paths, against the SAME global ledger).

    Works identically whether `summary` holds a file's FULL totals (a full
    parse) or just one increment's DELTA (an incremental parse) -- either
    way it only touches `summary.message_usage`/`tokens`/`cost`/
    `hourly_tokens`.

    A file re-parsing itself always owns its own previously-claimed ids, so
    incremental re-ingest of a single growing file stays additive and
    idempotent.
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
    session: AsyncSession,
    hour_key_id: str,
    repo: str,
    hourly: dict,
    *,
    full_replace: bool = False,
) -> None:
    """REPLACE per-hour token buckets for one SessionHourRow "owner" key (a
    real session_id, or a synthetic subagent key from _subagent_hour_key)
    with the given (authoritative, full-file) totals.

    By default (`full_replace=False`), only the exact hour keys present in
    `hourly` are touched -- never the owner's other hours, so a smaller file
    processed after a bigger one can't erase data the bigger file already
    wrote for a different hour.

    When `full_replace=True` (a genuine full reparse of the exact file that
    exclusively owns `hour_key_id` -- a shrink/replace/rebuild, not a race
    between two different files sharing a session_id), ALL of that owner's
    existing hour rows are deleted first, including hours no longer present
    in `hourly` at all. Without this, an hour the file used to cover before
    shrinking keeps its stale tokens forever, inflating the heatmap and 48h
    charts. Deletion happens even if `hourly` ends up empty (e.g. the file
    shrank to nothing usable), since the goal is to drop stale hours, not
    just skip writing new ones.

    Used by the FULL-parse path, where `hourly` is the file's complete,
    just-recomputed total for each hour it touches. For the incremental
    path, see `_add_hourly` instead -- replacing here would drop whatever a
    prior increment already accumulated for the same hour.
    """
    if full_replace:
        await session.execute(delete(SessionHourRow).where(SessionHourRow.session_id == hour_key_id))
    elif hourly:
        await session.execute(
            delete(SessionHourRow).where(
                SessionHourRow.session_id == hour_key_id,
                SessionHourRow.hour_ts.in_(list(hourly.keys())),
            )
        )
    if not hourly:
        return
    for hour_ts, tok in hourly.items():
        if tok <= 0:
            continue
        session.add(SessionHourRow(session_id=hour_key_id, repo=repo, hour_ts=hour_ts, tokens=tok))


async def _add_hourly(session: AsyncSession, hour_key_id: str, repo: str, hourly: dict) -> None:
    """ADD a delta on top of whatever per-hour tokens are already stored for
    each hour key present in `hourly`. Used by the incremental-delta path,
    where `hourly` is only the NEW tokens this increment contributed -- a
    delete-then-replace (see `_upsert_hourly`) would discard whatever an
    earlier increment already accumulated for the same hour.
    """
    if not hourly:
        return
    for hour_ts, tok in hourly.items():
        if tok <= 0:
            continue
        existing = (await session.execute(
            select(SessionHourRow).where(
                SessionHourRow.session_id == hour_key_id, SessionHourRow.hour_ts == hour_ts
            )
        )).scalar_one_or_none()
        if existing is not None:
            existing.tokens += tok
        else:
            session.add(SessionHourRow(session_id=hour_key_id, repo=repo, hour_ts=hour_ts, tokens=tok))


async def _upsert_file_state(
    session: AsyncSession,
    path_str: str,
    *,
    byte_offset: int,
    size: int,
    mtime: float,
    inode: int | None,
    session_id: str | None,
    is_subagent: bool,
) -> None:
    row = await session.get(IngestFileStateRow, path_str)
    if row is None:
        session.add(IngestFileStateRow(
            file_path=path_str, byte_offset=byte_offset, size=size, mtime=mtime,
            inode=inode, session_id=session_id, is_subagent=is_subagent,
        ))
    else:
        row.byte_offset = byte_offset
        row.size = size
        row.mtime = mtime
        row.inode = inode
        row.session_id = session_id
        row.is_subagent = is_subagent


def _scan_candidates(
    projects_dir: Path, cutoff: datetime | None, only: list[Path] | None = None
) -> tuple[list[tuple[Path, object]], int]:
    """Sync -- always invoked via `asyncio.to_thread` so a slow/networked
    walk of thousands of files never blocks the event loop.

    Stats every candidate ONCE here (returned to the caller so per-file
    processing never has to stat() again) and applies the cutoff filter
    BEFORE sorting -- a since_hours-scoped sweep would otherwise walk and
    sort every file in the whole corpus just to compute a sort key for
    files it's about to skip anyway.

    `only`, when given (the event-driven path: exact paths the watcher just
    reported), bypasses BOTH the corpus walk and the cutoff filter -- those
    paths are processed regardless of age.

    Oldest-mtime-first so that when two files share an assistant
    message.id (a resumed session copying forward earlier turns into a new
    file), the chronologically-original file is the one that claims it in
    message_ledger and the newer copy is the one that gets deduped --
    otherwise ownership on a full rebuild would depend on directory walk
    order, which is arbitrary.
    """
    paths: Iterable[Path] = only if only is not None else iter_jsonl_files(projects_dir)
    candidates: list[tuple[Path, object]] = []
    skipped = 0
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            continue
        if only is None and cutoff and datetime.fromtimestamp(st.st_mtime, tz=UTC) < cutoff:
            skipped += 1
            continue
        candidates.append((path, st))
    candidates.sort(key=lambda item: item[1].st_mtime)
    return candidates, skipped


@dataclass
class _Outcome:
    new: int = 0
    updated: int = 0
    skipped: int = 0
    events: int = 0


async def _apply_full_summary(
    session: AsyncSession,
    path: Path,
    repo_paths: list[Path],
    *,
    stat_tuple: tuple[float, int, int | None],
) -> _Outcome:
    """Full (re)parse of `path` from byte 0. Used for a brand-new file, a
    version-triggered/explicit rebuild, and a shrink/replace -- in every
    case the fresh parse's totals REPLACE (not add to) whatever this file
    previously contributed, including its message_ledger ownership rows
    (dropped unconditionally below; a no-op for a genuinely new file since
    it can't own any yet).
    """
    mtime, size, inode = stat_tuple
    path_str = str(path)
    is_subagent = "subagents" in path.parts
    outcome = _Outcome()

    # Read via the SAME bounded, offset-aware parser as the incremental path
    # (starting at 0 with an empty seed) rather than the unbounded
    # `parse_jsonl` -- two reasons:
    #  1. It only advances to the last COMPLETE newline, so a file that is
    #     mid-write on its very first ingest (a brand-new session file is
    #     often actively growing the moment it's discovered) leaves its
    #     trailing partial line unread instead of silently dropping it
    #     (parse_jsonl would try to json.loads() it, fail, and skip it --
    #     but with no offset to resume from, that content would never be
    #     retried).
    #  2. `result.new_offset` tells us EXACTLY how many bytes were consumed,
    #     even if the file grew between the stat() above and this read
    #     completing -- storing the pre-read `size` as the cursor instead
    #     would understate it and cause the next incremental tick to
    #     re-read (and double-count) bytes this full parse already counted.
    result = await asyncio.to_thread(parse_jsonl_incremental, path, repo_paths, 0, set())
    if result.summary is None:
        return outcome
    summary = result.summary
    events = result.events
    new_offset = result.new_offset
    stored_size = max(size, new_offset)

    # A full (re)parse always REPLACES this file's prior contribution.
    await session.execute(delete(MessageLedgerRow).where(MessageLedgerRow.file_path == path_str))

    if is_subagent:
        meta_path = path.with_suffix("").with_suffix(".meta.json")
        agent_type = summary.agent or "unknown"
        try:
            meta = json.loads(meta_path.read_text())
            agent_type = meta.get("agentType") or agent_type
        except Exception:  # noqa: BLE001
            pass

        await _reconcile_message_ledger(session, summary, path_str)

        existing_sc = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.file_path == path_str)
        )).scalar_one_or_none()
        if existing_sc:
            existing_sc.agent_type = agent_type
            existing_sc.tokens = summary.tokens
            existing_sc.cost = summary.cost
            existing_sc.file_mtime = mtime
            outcome.updated = 1
        else:
            session.add(SubagentCallRow(
                session_id=summary.session_id,
                agent_type=agent_type,
                repo=summary.repo,
                tokens=summary.tokens,
                cost=summary.cost,
                started_at=summary.started_at,
                file_path=path_str,
                file_mtime=mtime,
            ))
            outcome.new = 1

        # A subagent's _subagent_hour_key is owned exclusively by this one
        # file (see _subagent_hour_key docstring), and this whole branch is
        # always a full reparse -- so the fresh totals must fully replace
        # ALL of this key's prior hours, not just the ones `hourly` still
        # covers, or an hour the file shrank away from keeps stale tokens.
        await _upsert_hourly(
            session, _subagent_hour_key(path), summary.repo, summary.hourly_tokens, full_replace=True
        )
        await _upsert_file_state(
            session, path_str, byte_offset=new_offset, size=stored_size, mtime=mtime, inode=inode,
            session_id=summary.session_id, is_subagent=True,
        )
        await session.commit()
        return outcome

    # ---- session_summary branch ----
    now_ts = time.time()
    summary.status = "running" if now_ts - mtime < 60 else "completed"

    await _reconcile_message_ledger(session, summary, path_str)

    existing = await session.get(SessionSummaryRow, summary.session_id)
    # Captured BEFORE any mutation of `existing.file_path` below -- true only
    # for a genuine full reparse of the SAME file this session_id already
    # tracks (a shrink/replace), as opposed to a brand-new session_id or a
    # different file racing for the same one. Only in that genuine case can
    # this file's fresh hourly totals be trusted to fully replace ALL of
    # this session_id's stored hours -- see the `_upsert_hourly(...,
    # full_replace=...)` call below.
    is_same_file_full_reparse = existing is not None and existing.file_path == path_str
    content_win: bool
    if existing:
        # A full reparse of the SAME file this row already tracks (a
        # shrink/replace, or the brand-new-file case where `existing` is
        # some other belt-and-suspenders same-session_id race) is always
        # authoritative for that file's content and must win even if the
        # new content happens to be SMALLER (a legitimate shrink). Only
        # fall back to "prefer the richer file" when a genuinely DIFFERENT
        # file claims the same session_id -- that's the actual race this
        # heuristic exists for.
        content_win = existing.file_path == path_str or summary.tokens >= existing.tokens
        if content_win:
            existing.repo = summary.repo
            existing.started_at = summary.started_at
            existing.agent = summary.agent
            existing.task = summary.task
            existing.tokens = summary.tokens
            existing.cost = summary.cost
            existing.edits = summary.edits
            existing.file_path = path_str
            await session.execute(
                delete(LiveEventRow).where(LiveEventRow.session_id == summary.session_id)
            )
        _existing_ts = existing.last_event_at
        if _existing_ts.tzinfo is None:
            _existing_ts = _existing_ts.replace(tzinfo=UTC)
        if summary.last_event_at > _existing_ts:
            existing.last_event_at = summary.last_event_at
        existing.status = summary.status
        existing.file_mtime = mtime
        outcome.updated = 1
    else:
        content_win = True
        session.add(SessionSummaryRow(
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
            file_path=path_str,
            file_mtime=mtime,
        ))
        outcome.new = 1

    # Only a genuine full reparse of the SAME file already tracked for this
    # session_id may wipe ALL of its stored hours -- a brand-new session_id
    # or a different file losing the "richer file wins" race must not erase
    # hours some other file legitimately owns.
    await _upsert_hourly(
        session, summary.session_id, summary.repo, summary.hourly_tokens,
        full_replace=is_same_file_full_reparse,
    )

    if content_win:
        for ev in events:
            session.add(LiveEventRow(
                session_id=summary.session_id, repo=summary.repo, ts=ev.ts, kind=ev.kind,
                payload=json.dumps(ev.payload),
            ))
            outcome.events += 1

    await _upsert_file_state(
        session, path_str, byte_offset=new_offset, size=stored_size, mtime=mtime, inode=inode,
        session_id=summary.session_id, is_subagent=False,
    )
    await session.commit()
    return outcome


async def _apply_incremental_delta(
    session: AsyncSession,
    path: Path,
    repo_paths: list[Path],
    *,
    state: IngestFileStateRow,
    stat_tuple: tuple[float, int, int | None],
) -> _Outcome:
    """Parse only the bytes appended since `state.byte_offset` and merge the
    delta additively onto the existing SessionSummaryRow/SubagentCallRow.
    """
    mtime, size, inode = stat_tuple
    path_str = str(path)
    outcome = _Outcome()
    is_subagent = state.is_subagent

    if is_subagent:
        existing_row = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.file_path == path_str)
        )).scalar_one_or_none()
    else:
        existing_row = (
            await session.get(SessionSummaryRow, state.session_id) if state.session_id else None
        )

    if existing_row is None:
        # The cursor exists but its target row doesn't (e.g. manual DB
        # surgery, or a partial rebuild that wiped session_summary /
        # subagent_call without touching ingest_file_state) -- fall back to
        # a full parse instead of merging a delta onto nothing.
        return await _apply_full_summary(session, path, repo_paths, stat_tuple=stat_tuple)

    prior_agent = None if is_subagent else existing_row.agent
    prior_task = None if is_subagent else existing_row.task
    prior_repo = existing_row.repo

    seed_ids = set((await session.execute(
        select(MessageLedgerRow.message_id).where(MessageLedgerRow.file_path == path_str)
    )).scalars().all())

    result = await asyncio.to_thread(
        parse_jsonl_incremental,
        path,
        repo_paths,
        state.byte_offset,
        seed_ids,
        session_id=state.session_id,
        repo=prior_repo,
        agent_name=prior_agent,
        task_text=prior_task,
    )

    if result.new_offset == state.byte_offset:
        # No complete new line yet (a trailing partial line with no \n) --
        # leave file-state untouched entirely so the next tick's stat-only
        # skip check re-detects the size/mtime change and retries the
        # still-unread bytes instead of "forgetting" them.
        outcome.skipped = 1
        return outcome

    if is_subagent:
        existing_row.file_mtime = mtime
    else:
        existing_row.repo = result.repo
        existing_row.agent = result.agent_name
        existing_row.task = result.task_text
        existing_row.file_mtime = mtime
        now_ts = time.time()
        existing_row.status = "running" if now_ts - mtime < 60 else "completed"
        if result.last_ts is not None:
            _existing_ts = existing_row.last_event_at
            if _existing_ts.tzinfo is None:
                _existing_ts = _existing_ts.replace(tzinfo=UTC)
            if result.last_ts > _existing_ts:
                existing_row.last_event_at = result.last_ts

    if result.summary is not None:
        delta = result.summary
        await _reconcile_message_ledger(session, delta, path_str)
        if is_subagent:
            existing_row.tokens += delta.tokens
            existing_row.cost = round(existing_row.cost + delta.cost, 4)
            await _add_hourly(session, _subagent_hour_key(path), result.repo, delta.hourly_tokens)
        else:
            existing_row.tokens += delta.tokens
            existing_row.cost = round(existing_row.cost + delta.cost, 4)
            existing_row.edits += delta.edits
            await _add_hourly(session, state.session_id, result.repo, delta.hourly_tokens)
            for ev in result.events:
                session.add(LiveEventRow(
                    session_id=state.session_id, repo=result.repo, ts=ev.ts, kind=ev.kind,
                    payload=json.dumps(ev.payload),
                ))
                outcome.events += 1

    outcome.updated = 1
    await _upsert_file_state(
        session, path_str, byte_offset=result.new_offset, size=max(size, result.new_offset),
        mtime=mtime, inode=inode, session_id=state.session_id, is_subagent=is_subagent,
    )
    await session.commit()
    return outcome


async def _ingest_one_file(
    session: AsyncSession,
    path: Path,
    repo_paths: list[Path],
    *,
    rebuild: bool,
    state_by_path: dict[str, IngestFileStateRow],
    stat_result,
) -> _Outcome:
    """The skip/incremental/full decision for one file. `stat_result` is
    ALWAYS pre-fetched by `_scan_candidates` (off-loop) -- this function
    never calls `path.stat()` or opens the file itself; that only happens
    (via asyncio.to_thread) inside `_apply_full_summary`/
    `_apply_incremental_delta` once we've already decided real work is
    needed.
    """
    if "subagents" in path.parts:
        stem_id = path.stem[len("agent-"):] if path.stem.startswith("agent-") else path.stem
        if any(stem_id.startswith(p) for p in _INTERNAL_SUBAGENT_PREFIXES):
            return _Outcome(skipped=1)

    path_str = str(path)
    mtime, size, inode = stat_result.st_mtime, stat_result.st_size, (stat_result.st_ino or None)

    existing_state = None if rebuild else state_by_path.get(path_str)

    if (
        existing_state is not None
        and size == existing_state.size
        and abs(mtime - existing_state.mtime) < 0.5
    ):
        # The skip decision -- made purely from the stat() `_scan_candidates`
        # already did plus this in-memory dict lookup -- happens BEFORE any
        # open()/parse call. No I/O at all for the overwhelmingly common
        # unchanged case. Size compares exact (it's an integer); mtime keeps
        # the same sub-second tolerance the pre-incremental code used, since
        # size alone already rules out any genuine content change.
        return _Outcome(skipped=1)

    is_replace = existing_state is not None and (
        size < existing_state.byte_offset
        or (inode and existing_state.inode and inode != existing_state.inode)
    )

    if rebuild or existing_state is None or is_replace:
        return await _apply_full_summary(session, path, repo_paths, stat_tuple=(mtime, size, inode))

    return await _apply_incremental_delta(
        session, path, repo_paths, state=existing_state, stat_tuple=(mtime, size, inode)
    )


async def ingest_all(
    since_hours: int | None = None,
    rebuild: bool = False,
    changed_paths: Iterable[Path] | None = None,
) -> dict:
    """Walk projects_dir (or, when `changed_paths` is given, just those exact
    files) and upsert rows.

    `changed_paths` is the event-driven path: the live_stream watcher signals
    exactly which files changed, so a tick can skip the corpus walk entirely
    and touch only those paths. Ignored when `rebuild` ends up true (a
    rebuild always needs the full corpus).
    """
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
            # whatever `since_hours`/`changed_paths` scope the caller asked
            # for -- we're about to wipe everything below. The version
            # marker itself is only written at the very end of this
            # function, after the walk completes without raising -- see the
            # `if version_rebuild:` block near the bottom. A crash mid-
            # rebuild (plausible on a multi-GB / thousands-of-files corpus)
            # must leave the marker stale/missing so the NEXT ingest_all()
            # call detects it and rebuilds again, instead of believing a
            # half-finished DB is already healed.
            rebuild = True
            cutoff = None
            logger.info("ingest logic version changed -> rebuilding JSONL-derived tables")

        if rebuild:
            changed_paths = None
            # JSONL-derived tables ONLY -- never otel_event/otel_metric (a
            # separate OTLP-fed pipeline) and never the repo registry (a JSON
            # file, not a DB table at all).
            await session.execute(delete(LiveEventRow))
            await session.execute(delete(SessionSummaryRow))
            await session.execute(delete(SessionHourRow))
            await session.execute(delete(SubagentCallRow))
            await session.execute(delete(MessageLedgerRow))
            await session.execute(delete(IngestFileStateRow))
            await session.commit()

        only = None
        if changed_paths is not None:
            only = sorted({p for p in changed_paths if p.suffix == ".jsonl"})

        # Off-loop: the corpus walk + per-file stat() (or, for the
        # event-driven path, just stat()-ing the handful of changed paths)
        # never blocks the event loop, regardless of filesystem speed.
        scanned, cutoff_skipped = await asyncio.to_thread(
            _scan_candidates, settings.projects_dir, cutoff, only
        )
        skipped += cutoff_skipped
        candidates = [p for p, _st in scanned]
        stat_by_path = dict(scanned)

        # Preload existing file-state cursors in bulk -- avoids one DB
        # round-trip per candidate for the (common) unchanged-file case.
        state_by_path: dict[str, IngestFileStateRow] = {}
        if candidates and not rebuild:
            path_strs = [str(p) for p in candidates]
            for i in range(0, len(path_strs), _LEDGER_LOOKUP_CHUNK):
                chunk = path_strs[i:i + _LEDGER_LOOKUP_CHUNK]
                rows = (await session.execute(
                    select(IngestFileStateRow).where(IngestFileStateRow.file_path.in_(chunk))
                )).scalars().all()
                state_by_path.update({r.file_path: r for r in rows})

        for path in candidates:
            outcome = await _ingest_one_file(
                session, path, repo_paths,
                rebuild=rebuild,
                state_by_path=state_by_path,
                stat_result=stat_by_path[path],
            )
            new_count += outcome.new
            updated_count += outcome.updated
            skipped += outcome.skipped
            event_count += outcome.events

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
