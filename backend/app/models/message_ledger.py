"""Global ledger of assistant message ids already attributed to a file.

Claude Code can write the same assistant message id into more than one JSONL
file: a resumed session copies forward earlier turns into a new top-level
file, and (rarely) a broadcast system message lands identically in several
concurrently-open sessions. Without this ledger, ingest.py would sum that
message's tokens/cost once per file it appears in.

The rule is "first file to claim a message id owns it": whichever file is
ingested first for a given message_id keeps its tokens/cost; every other
file that later encounters the same message_id has that message's
contribution subtracted from its own totals before it's persisted. A file
re-parsing itself (mtime changed, still growing) always owns its own
previously-claimed ids, so incremental re-ingest stays idempotent.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, Integer, String

from app.db import Base


class MessageLedgerRow(Base):
    __tablename__ = "message_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String, nullable=False, unique=True, index=True)
    # Absolute path of the file that first counted this message's tokens.
    file_path = Column(String, nullable=False, index=True)
    tokens = Column(BigInteger, default=0)
