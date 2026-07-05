"""Atomic settings.json writer for the permissions editor.

Safety rules:
1. Always write to a temp file in the same directory + rename. Same-dir
   rename is atomic on POSIX; failed writes leave the original intact.
2. Always make a backup before writing: `<file>.bak.<unix-timestamp>`.
   Old backups are pruned to a fixed window so we don't accumulate forever.
3. Optional `if_unchanged_since` for external-edit detection. If the
   file's mtime is past this value, raise StaleFile so the client can
   refresh and retry without clobbering an out-of-band edit.
4. Preserve every other key in the JSON. Only the `permissions` block
   is replaced. Insertion order is preserved as much as Python's dict
   ordering allows (3.7+ guarantees insertion order).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

BACKUP_KEEP = 10
ALLOWED_TARGETS = ("settings", "settings_local")


class StaleFile(Exception):
    """Raised when the file changed on disk since the client last read it."""


class ScopeNotFound(Exception):
    """Raised when the requested scope (repo id) doesn't resolve to a path."""


def _resolve_scope_dir(scope: str) -> Path:
    """Return the .claude directory for the given scope.

    - "global" / "~"  -> ~/.claude/
    - <repo_id>       -> <repo_path>/.claude/  (looked up in repo_registry)
    """
    settings = get_settings()
    if scope in ("global", "~", ""):
        return settings.claude_dir
    # Lazy import to avoid circular dep with repo_registry
    from app.services.repo_registry import all_repo_paths
    for repo_path in all_repo_paths():
        if repo_path.name == scope:
            return repo_path / ".claude"
    raise ScopeNotFound(f"unknown scope: {scope}")


def resolve_settings_path(scope: str, target: str) -> Path:
    """Compute the absolute path for a (scope, target) pair.

    target must be one of ALLOWED_TARGETS:
      - "settings"       -> settings.json       (checked-in)
      - "settings_local" -> settings.local.json (gitignored, default)
    """
    if target not in ALLOWED_TARGETS:
        raise ValueError(f"target must be one of {ALLOWED_TARGETS}, got {target!r}")
    base = _resolve_scope_dir(scope)
    filename = "settings.json" if target == "settings" else "settings.local.json"
    return base / filename


def _read_json_if_present(path: Path) -> dict:
    """Load JSON from path, returning {} if the file is missing or empty.

    Malformed JSON is treated as an error — we don't silently overwrite
    a broken-but-existing file. The caller should surface the parse error.
    """
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    return json.loads(raw)


def read_permissions(scope: str, target: str) -> dict:
    """Return {scope, target, file_path, file_exists, mtime, permissions}."""
    path = resolve_settings_path(scope, target)
    exists = path.is_file()
    mtime = path.stat().st_mtime if exists else 0.0
    data: dict = {}
    if exists:
        try:
            data = _read_json_if_present(path)
        except json.JSONDecodeError as e:
            logger.warning("malformed JSON in %s: %s", path, e)
            data = {}
    perms = data.get("permissions") or {}
    return {
        "scope": scope,
        "target": target,
        "file_path": str(path),
        "file_exists": exists,
        "mtime": mtime,
        "permissions": {
            "allow": list(perms.get("allow") or []),
            "deny": list(perms.get("deny") or []),
            "ask": list(perms.get("ask") or []),
        },
    }


def _prune_backups(path: Path, keep: int = BACKUP_KEEP) -> None:
    """Keep only the most recent `keep` backups for this file."""
    stem = path.name + ".bak."
    backups = sorted(
        (p for p in path.parent.iterdir() if p.name.startswith(stem)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            logger.debug("could not prune backup %s", old)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write data to a same-dir temp file then rename over `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def write_permissions(
    scope: str,
    target: str,
    permissions: dict,
    if_unchanged_since: float | None = None,
) -> dict:
    """Replace the permissions block in (scope, target)'s settings file.

    Returns {file_path, mtime, backup_path}. Raises StaleFile if the
    on-disk mtime exceeds `if_unchanged_since`. Always makes a backup
    when the file already exists.
    """
    path = resolve_settings_path(scope, target)
    existed = path.is_file()

    if existed and if_unchanged_since is not None:
        current = path.stat().st_mtime
        # Tiny epsilon to absorb sub-millisecond FS granularity differences.
        if current > if_unchanged_since + 0.001:
            raise StaleFile(
                f"file changed on disk (mtime {current} > expected {if_unchanged_since})"
            )

    existing: dict = {}
    if existed:
        try:
            existing = _read_json_if_present(path)
        except json.JSONDecodeError:
            # Refuse to clobber an unparseable file — bubble up so the user
            # can fix it manually instead of losing arbitrary content.
            raise

    # Preserve everything except `permissions`. The permissions block
    # is normalized: only allow / deny / ask, in that bucket order,
    # each list deduplicated while preserving the first-seen order.
    def _dedupe(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in seq:
            s = str(item).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    existing["permissions"] = {
        "allow": _dedupe(permissions.get("allow") or []),
        "deny": _dedupe(permissions.get("deny") or []),
        "ask": _dedupe(permissions.get("ask") or []),
    }

    # Backup BEFORE we touch anything.
    backup_path = ""
    if existed:
        backup_path = str(path) + f".bak.{int(time.time())}"
        try:
            Path(backup_path).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            _prune_backups(path)
        except OSError as e:
            logger.warning("backup failed for %s: %s — proceeding anyway", path, e)
            backup_path = ""

    _atomic_write_json(path, existing)
    new_mtime = path.stat().st_mtime
    return {
        "file_path": str(path),
        "mtime": new_mtime,
        "backup_path": backup_path,
    }
