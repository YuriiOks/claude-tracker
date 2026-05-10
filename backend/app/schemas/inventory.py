from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.repo import GlobalScope


class FileSizes(BaseModel):
    agents: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    commands: dict[str, int] = Field(default_factory=dict)
    rules: dict[str, int] = Field(default_factory=dict)
    hooks: dict[str, int] = Field(default_factory=dict)


class PermissionsDetail(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class GlobalEnvelope(GlobalScope):
    """GLOBAL plus computed file sizes."""
    file_sizes: FileSizes = Field(default_factory=FileSizes)
