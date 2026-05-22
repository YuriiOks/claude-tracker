from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.repo import GlobalScope


class FileSizes(BaseModel):
    agents: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    commands: dict[str, int] = Field(default_factory=dict)
    rules: dict[str, int] = Field(default_factory=dict)
    hooks: dict[str, int] = Field(default_factory=dict)
    # Additive: matches the official Claude Code .claude/ layout (since v2)
    # plus our project's custom contexts/. Empty for most projects -- still
    # surfaced so the tree shows what slots exist.
    output_styles: dict[str, int] = Field(default_factory=dict, alias="outputStyles")
    agent_memory: dict[str, int] = Field(default_factory=dict, alias="agentMemory")
    contexts: dict[str, int] = Field(default_factory=dict)


class PermissionsDetail(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class GlobalEnvelope(GlobalScope):
    """GLOBAL plus computed file sizes (camelCase alias for the wire)."""
    file_sizes: FileSizes = Field(default_factory=FileSizes, alias="fileSizes")
