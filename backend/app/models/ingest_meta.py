"""Singleton row tracking the ingest logic version.

When `app.services.ingest.INGEST_VERSION` is bumped (i.e. the JSONL -> SQL
derivation rules changed in a way that makes previously-ingested rows stale
or wrong), `ingest_all()` notices the stored version is behind, wipes the
JSONL-derived tables, and re-ingests everything from scratch exactly once.
Never touches otel_event/otel_metric or the repo registry (a JSON file, not
a DB table) -- only session_summary / session_hour / subagent_call /
live_event / message_ledger are JSONL-derived.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer

from app.db import Base

# Fixed primary key -- there is only ever one row in this table.
SINGLETON_ID = 1


class IngestMetaRow(Base):
    __tablename__ = "ingest_meta"

    id = Column(Integer, primary_key=True, default=SINGLETON_ID)
    version = Column(Integer, nullable=False, default=0)
