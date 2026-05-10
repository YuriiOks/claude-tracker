"""Pydantic models mirroring src/data.js Repo / GLOBAL shapes 1:1."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Permissions(_AliasModel):
    allow: int = 0
    deny: int = 0
    ask: int = 0


class RepoStats(_AliasModel):
    sessions_today: int = Field(default=0, alias="sessionsToday")
    sessions_week: int = Field(default=0, alias="sessionsWeek")
    tokens_week: int = Field(default=0, alias="tokensWeek")
    cost_week: float = Field(default=0.0, alias="costWeek")
    files_edited: int = Field(default=0, alias="filesEdited")
    avg_session: str = Field(default="—", alias="avgSession")


class Repo(_AliasModel):
    id: str
    name: str
    org: str = "personal"
    path: str
    description: str = ""
    branch: str = "main"
    language: str = ""
    accent: str = "#6a8caf"
    is_active: bool = Field(default=False, alias="isActive")
    stats: RepoStats = Field(default_factory=RepoStats)
    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)


class GlobalScope(_AliasModel):
    id: str = "global"
    name: str = "~/.claude (global)"
    path: str = "~/.claude"
    description: str = "Global Claude Code setup — applies to every repo"
    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
