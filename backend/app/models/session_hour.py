"""Per-hour token aggregates — one row per (session × UTC hour)."""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String

from app.db import Base


class SessionHourRow(Base):
    __tablename__ = "session_hour"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    repo = Column(String, nullable=False)
    # UTC datetime truncated to the start of the hour.
    hour_ts = Column(DateTime, nullable=False)
    tokens = Column(BigInteger, default=0)

    __table_args__ = (
        Index("ix_session_hour_ts", "hour_ts"),
        Index("ix_session_hour_sid_ts", "session_id", "hour_ts", unique=True),
    )
