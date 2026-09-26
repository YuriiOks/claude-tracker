from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentCall(BaseModel):
    """One recent subagent invocation, for the agent-detail page."""
    model_config = ConfigDict(populate_by_name=True)
    repo: str = ""
    tokens: int = 0
    cost: float = 0.0
    started_at: str = Field(default="", alias="startedAt")
    session_id: str = Field(default="", alias="sessionId")


class AgentMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    repo: str
    role: str = ""
    tools: list[str] = Field(default_factory=list)
    delegates: list[str] = Field(default_factory=list)
    calls_today: int = Field(default=0, alias="callsToday")
    avg_tokens: int = Field(default=0, alias="avgTokens")
    calls_week: int = Field(default=0, alias="callsWeek")
    calls_total: int = Field(default=0, alias="callsTotal")
    recent_calls: list[AgentCall] = Field(default_factory=list, alias="recentCalls")
