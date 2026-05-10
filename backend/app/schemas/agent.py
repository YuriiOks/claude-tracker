from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    repo: str
    role: str = ""
    tools: list[str] = Field(default_factory=list)
    delegates: list[str] = Field(default_factory=list)
    calls_today: int = Field(default=0, alias="callsToday")
    avg_tokens: int = Field(default=0, alias="avgTokens")
