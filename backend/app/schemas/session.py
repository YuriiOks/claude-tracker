from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Session(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    repo: str
    started: str
    duration: str
    agent: str = ""
    task: str = ""
    status: Literal["running", "completed", "failed"] = "completed"
    tokens: int = 0
    cost: float = 0.0
    edits: int = 0


class DiffLine(BaseModel):
    type: Literal["ctx", "add", "del"]
    text: str


class DiffHunk(BaseModel):
    header: str
    lines: list[DiffLine] = Field(default_factory=list)


class Diff(BaseModel):
    file: str
    agent: str = ""
    session: str = ""
    hunks: list[DiffHunk] = Field(default_factory=list)


class RecentDiffItem(BaseModel):
    """One row in the /diff page's "Recent diffs across repos" list.

    Carries typed primitives (ISO timestamp + numeric line counts) rather
    than pre-formatted strings so the frontend can re-render elapsed time
    on each tick and so future sort/filter work doesn't need to re-parse
    "+12 −2" or "2m".
    """
    ts: datetime
    file: str
    repo: str
    adds: int = 0
    dels: int = 0
    agent: str = ""

