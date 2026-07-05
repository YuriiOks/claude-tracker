"""One row per subagent JSONL file invocation."""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String

from app.db import Base


class SubagentCallRow(Base):
    __tablename__ = "subagent_call"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    # agent_type index declared in __table_args__ — do NOT also set index=True
    # here, that would create a duplicate name and crash create_all on fresh DBs.
    agent_type = Column(String, nullable=False)
    repo = Column(String, nullable=False)
    tokens = Column(BigInteger, default=0)
    cost = Column(Float, default=0.0)
    started_at = Column(DateTime, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_mtime = Column(Float, default=0.0)

    __table_args__ = (
        Index("ix_subagent_call_agent_type", "agent_type"),
        Index("ix_subagent_call_started", "started_at"),
    )
