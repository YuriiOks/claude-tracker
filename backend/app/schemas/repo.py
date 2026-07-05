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
    spark: list[int] = Field(default_factory=list)


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
    # Additive Claude Code folders (since v2.x). hooks: shell/python/js
    # files run on PostToolUse / Stop / SessionStart events. output_styles:
    # response-formatting templates. agent_memory: per-agent MEMORY.md
    # under <agent-name>/. contexts: custom convention in this repo.
    hooks: list[str] = Field(default_factory=list)
    output_styles: list[str] = Field(default_factory=list, alias="outputStyles")
    agent_memory: list[str] = Field(default_factory=list, alias="agentMemory")
    contexts: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)
    # Project-root files that Claude Code reads at session start (CLAUDE.md,
    # .mcp.json, .worktreeinclude) plus the repo's own conventions
    # (ERRORS.md, MASTER_PLAN.md). Only names that actually exist are listed.
    root_files: list[str] = Field(default_factory=list, alias="rootFiles")
    permissions: Permissions = Field(default_factory=Permissions)


class GlobalScope(_AliasModel):
    id: str = "global"
    name: str = "~/.claude (global)"
    path: str = "~/.claude"
    description: str = "Global Claude Code setup — applies to every repo"
    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    output_styles: list[str] = Field(default_factory=list, alias="outputStyles")
    agent_memory: list[str] = Field(default_factory=list, alias="agentMemory")
    plugins: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
