"""Runtime registry for tracked repos.

Combines:
- REPO_ROOTS from env (set in .env.docker, requires container restart to change)
- A persistent JSON file at <db_path parent>/tracked-repos.json that can be
  written at runtime via POST /api/repos.

This means users can add new repos via the UI without rebuilding or restarting
the container — the next /api/repos GET picks up additions immediately.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

_RUNTIME_FILE_NAME = "tracked-repos.json"

# Guards the read-modify-write in add_repo/remove_repo. These are plain sync
# functions called from async route handlers without an await point, but a
# thread lock is used (rather than asyncio.Lock) so the guarantee holds even
# if a caller ever moves this onto a worker thread.
_registry_lock = threading.Lock()


def _runtime_file() -> Path:
    settings = get_settings()
    return settings.db_path.parent / _RUNTIME_FILE_NAME


def _read_runtime() -> list[str]:
    f = _runtime_file()
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text())
        if isinstance(data, list):
            return [str(p) for p in data if isinstance(p, str)]
    except Exception as e:
        logger.warning("could not read %s: %s", f, e)
    return []


def _write_runtime(paths: list[str]) -> None:
    f = _runtime_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f"{f.suffix}.tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(json.dumps(sorted(set(paths)), indent=2))
    os.replace(tmp, f)


def all_repo_paths() -> list[Path]:
    """Env REPO_ROOTS + runtime additions, deduped, order preserved."""
    settings = get_settings()
    env_paths = [str(p) for p in settings.repo_paths]
    runtime_paths = _read_runtime()
    seen: set[str] = set()
    out: list[Path] = []
    for p in env_paths + runtime_paths:
        if p not in seen:
            seen.add(p)
            out.append(Path(p).expanduser())
    return out


def add_repo(path: str) -> bool:
    """Append a path to the runtime file. Returns True if newly added."""
    with _registry_lock:
        paths = _read_runtime()
        if path in paths:
            return False
        # Also skip if already in env REPO_ROOTS
        settings = get_settings()
        env_paths = [str(p) for p in settings.repo_paths]
        if path in env_paths:
            return False
        paths.append(path)
        _write_runtime(paths)
        return True


def remove_repo(path: str) -> bool:
    """Remove a path from the runtime file (env entries can't be removed)."""
    with _registry_lock:
        paths = _read_runtime()
        if path not in paths:
            return False
        paths.remove(path)
        _write_runtime(paths)
        return True
