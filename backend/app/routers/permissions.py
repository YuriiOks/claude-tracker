"""Permissions endpoints — aggregated view + scoped editor."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from app.schemas.inventory import PermissionsDetail
from app.schemas.permissions_edit import (
    ScopedPermissionsRead,
    ScopedPermissionsWrite,
    ScopedPermissionsWriteResult,
)
from app.services import permissions_writer as pw
from app.services.repo_scanner import collect_permissions_detail

logger = logging.getLogger(__name__)
router = APIRouter(tags=["permissions"])


@router.get("/permissions", response_model=PermissionsDetail)
async def get_permissions() -> PermissionsDetail:
    """Aggregated read across global + every repo. Unchanged from v1."""
    return collect_permissions_detail()


@router.get("/permissions/scoped", response_model=ScopedPermissionsRead)
async def get_scoped_permissions(
    scope: str = "global",
    target: str = "settings_local",
) -> ScopedPermissionsRead:
    """Read one specific settings file's permissions block.

    - scope: 'global' (~/.claude/) or a repo id from /api/repos.
    - target: 'settings' (committed) or 'settings_local' (gitignored, default).
    """
    try:
        data = pw.read_permissions(scope=scope, target=target)
    except pw.ScopeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ScopedPermissionsRead.model_validate(data)


@router.put("/permissions/scoped", response_model=ScopedPermissionsWriteResult)
async def put_scoped_permissions(
    body: ScopedPermissionsWrite,
) -> ScopedPermissionsWriteResult:
    """Replace the permissions block in the (scope, target) settings file.

    Atomically writes via temp-file + rename. Makes a `.bak.<ts>` backup
    of the previous contents (capped to a rolling window). If
    `ifUnchangedSince` is set and the on-disk mtime is newer, refuses
    with 409 so the client can refresh.
    """
    perms = {
        "allow": body.permissions.allow,
        "deny": body.permissions.deny,
        "ask": body.permissions.ask,
    }
    try:
        result = pw.write_permissions(
            scope=body.scope,
            target=body.target,
            permissions=perms,
            if_unchanged_since=body.if_unchanged_since,
        )
    except pw.ScopeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except pw.StaleFile as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=409,
            detail=f"settings file is not valid JSON; refusing to overwrite: {e}",
        ) from e
    return ScopedPermissionsWriteResult.model_validate(result)
