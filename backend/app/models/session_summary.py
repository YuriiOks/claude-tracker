from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SessionSummaryRow(Base):
    __tablename__ = "session_summary"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    repo: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    last_event_at: Mapped[datetime] = mapped_column(DateTime)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    task: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="completed")
    tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    edits: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str] = mapped_column(String)
    file_mtime: Mapped[float] = mapped_column(Float, default=0.0)
