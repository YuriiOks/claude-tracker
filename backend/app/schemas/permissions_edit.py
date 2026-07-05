"""Request / response models for editable permissions.

Three core operations land on the same shape: client sends the full
{allow, deny, ask} state it wants written. Server diffs against disk
and writes atomically. No per-rule add/move/delete endpoints — the
client tracks state locally and ships a single PUT on save.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ScopedPermissions(_AliasModel):
    """Permissions for one settings file (allow / deny / ask string lists)."""
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class ScopedPermissionsRead(_AliasModel):
    """GET response — permissions plus metadata about the file on disk."""
    scope: str = "global"
    target: str = "settings_local"          # "settings" | "settings_local"
    file_path: str = Field(default="", alias="filePath")
    file_exists: bool = Field(default=False, alias="fileExists")
    mtime: float = 0.0                       # epoch seconds; 0 if missing
    permissions: ScopedPermissions = Field(default_factory=ScopedPermissions)


class ScopedPermissionsWrite(_AliasModel):
    """PUT body — replace this file's permissions block."""
    scope: str = "global"
    target: str = "settings_local"
    permissions: ScopedPermissions
    # If set, server refuses the write when the file mtime has advanced
    # past this value. Prevents clobbering external edits.
    if_unchanged_since: float | None = Field(default=None, alias="ifUnchangedSince")


class ScopedPermissionsWriteResult(_AliasModel):
    """PUT response — new mtime so the client can keep its `ifUnchangedSince` fresh."""
    file_path: str = Field(default="", alias="filePath")
    mtime: float = 0.0
    backup_path: str = Field(default="", alias="backupPath")
