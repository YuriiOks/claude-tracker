from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventKind = Literal[
    "agent_start",
    "tool",
    "delegate",
    "skill",
    "permission",
    "command",
]


class LiveEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    t: int = 0
    repo: str
    kind: EventKind
    agent: str | None = None
    msg: str | None = None
    tool: str | None = None
    target: str | None = None
    skill: str | None = None
    cmd: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    level: Literal["allow", "deny", "ask"] | None = None
    action: str | None = None
    granted: bool | None = None
