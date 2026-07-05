"""OTel event rows — one row per logRecord received from Claude Code's OTLP exporter."""
from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OtelEventRow(Base):
    __tablename__ = "otel_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # UTC datetime — stored naive, treated as UTC everywhere.
    ts: Mapped[object] = mapped_column(DateTime, nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    prompt_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repo: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # All merged resource + record attributes as a JSON string, default "{}".
    attrs: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    __table_args__ = (
        # Idempotent re-export dedup: same session + same sequence = same event.
        # NULLs are exempt from uniqueness in SQLite — not a problem in practice
        # because every real Claude Code event carries both fields.
        UniqueConstraint("session_id", "event_sequence", name="uq_otel_event_sid_seq"),
    )
