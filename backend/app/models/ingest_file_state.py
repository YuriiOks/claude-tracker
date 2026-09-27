"""Per-file incremental-ingest cursor.

One row per JSONL file ever ingested — tracks how many bytes of it have
already been parsed and merged into session_summary / subagent_call /
session_hour / message_ledger, so a periodic or event-driven ingest tick can
tell "unchanged" (skip, no I/O beyond a stat()), "grew" (parse only the new
bytes), and "shrank/replaced" (full reparse that REPLACES this file's prior
contribution) apart — see app.services.ingest for the decision logic.

Wiped alongside every other JSONL-derived table on a `rebuild=True` walk or
an INGEST_VERSION bump (app.models.ingest_meta) — never touched by the
otel_event/otel_metric pipeline or the repo registry.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IngestFileStateRow(Base):
    __tablename__ = "ingest_file_state"

    file_path: Mapped[str] = mapped_column(String, primary_key=True)
    # Bytes already consumed and merged -- the next incremental parse seeks
    # here and reads onward. Never advanced past the last complete newline
    # (see jsonl_parser.parse_jsonl_incremental), so a trailing partial line
    # is naturally retried on the next tick instead of being lost.
    byte_offset: Mapped[int] = mapped_column(BigInteger, default=0)
    # File size + mtime as of the last successful (full or incremental)
    # parse -- an exact match on BOTH against the current stat() is the
    # "nothing changed, skip without opening the file" fast path.
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mtime: Mapped[float] = mapped_column(Float, default=0.0)
    # st_ino at last parse, when the platform provides a non-zero one -- a
    # change here despite size >= byte_offset means the path was replaced
    # (e.g. an atomic rename) rather than genuinely appended to.
    inode: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # The session_id this file resolved to on its first (full) parse -- kept
    # so an incremental tick can look up the existing SessionSummaryRow (or,
    # for subagent files, just informational) without re-reading the file
    # from byte 0 just to rediscover it.
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    is_subagent: Mapped[bool] = mapped_column(Boolean, default=False)
