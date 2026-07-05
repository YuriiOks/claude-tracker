from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.inventory import GlobalEnvelope
from app.schemas.repo import Repo
from app.services.repo_registry import add_repo as registry_add
from app.services.repo_registry import all_repo_paths
from app.services.repo_registry import remove_repo as registry_remove
from app.services.repo_scanner import get_repo_by_id, scan_all_repos, scan_global
from app.services.repo_stats import fetch_real_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["repos"])


@router.get("/repos", response_model=list[Repo])
async def list_repos() -> list[Repo]:
    repos = await asyncio.to_thread(scan_all_repos)
    real = await fetch_real_stats()
    for r in repos:
        if r.name in real:
            r.stats = real[r.name]
    return repos


@router.get("/repos/{repo_id}", response_model=Repo)
async def get_repo(repo_id: str) -> Repo:
    repo = await asyncio.to_thread(get_repo_by_id, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"repo not found: {repo_id}")
    real = await fetch_real_stats()
    if repo.name in real:
        repo.stats = real[repo.name]
    return repo


@router.get("/global", response_model=GlobalEnvelope)
async def get_global() -> GlobalEnvelope:
    return await asyncio.to_thread(scan_global)


# ----------------------- Add-repo discovery & writes ------------------------


def _cwd_from_project_dir(project_dir: Path) -> str:
    """Read JSONL transcripts to extract the real host cwd.

    Decoding the directory name itself is unreliable because Claude Code
    replaces both '/' AND '_' with '-' (so 'yurii_jupus' becomes 'yurii-jupus'
    and is unrecoverable). The `cwd` field in each JSONL record holds the
    canonical host path, so we read that instead.

    Older JSONL records may lack `cwd`, so we scan up to MAX_LINES per file
    and try newest files first.
    """
    import json
    MAX_LINES = 200
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda f: f.stat().st_mtime if f.exists() else 0,
        reverse=True,  # newest first
    )
    for jsonl in jsonl_files:
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= MAX_LINES:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = obj.get("cwd")
                    if cwd:
                        return str(cwd)
        except OSError:
            continue
    return ""


def _scan_repo_candidates() -> list[dict]:
    # Discover candidate repos by scanning ~/.claude/projects/. A path is a
    # valid candidate if (a) it exists on disk and (b) it contains a
    # .claude/ folder. Already-tracked paths are excluded. Returns:
    # [{ host_path, container_path, name, sessions, alreadyTracked }, ...]
    settings = get_settings()
    projects_dir = settings.projects_dir
    if not projects_dir.is_dir():
        return []

    tracked_container_paths = {str(p) for p in all_repo_paths()}
    out: list[dict] = []
    seen: set[str] = set()
    for child in sorted(projects_dir.iterdir()):
        if not child.is_dir():
            continue
        host_path = _cwd_from_project_dir(child)
        if not host_path or host_path in seen:
            continue
        seen.add(host_path)
        container_path = settings.translate_host_path(host_path)
        # Must exist on host (visible via /host/home mount) AND have .claude
        if not container_path.is_dir():
            continue
        if not (container_path / ".claude").is_dir():
            continue
        sessions = sum(1 for _ in child.glob("*.jsonl"))
        out.append({
            "hostPath": host_path,
            "containerPath": str(container_path),
            "name": Path(host_path).name,
            "sessions": sessions,
            "alreadyTracked": str(container_path) in tracked_container_paths,
        })
    return sorted(out, key=lambda r: (r["alreadyTracked"], -r["sessions"], r["name"]))


@router.get("/repos/candidates/list")
async def list_repo_candidates() -> list[dict]:
    """Discover candidate repos by scanning ~/.claude/projects/. A path is a
    valid candidate if (a) it exists on disk and (b) it contains a `.claude/`
    folder. Already-tracked paths are excluded.

    Returns: [{ host_path, container_path, name, sessions, alreadyTracked }, ...]
    """
    return await asyncio.to_thread(_scan_repo_candidates)


def _add_repo_sync(raw: str, settings) -> dict:
    # If it is a host path, translate. If it is already a container path, no-op.
    target = settings.translate_host_path(raw) if raw.startswith(settings.host_home or "/Users") else Path(raw)

    # C4: containment -- resolved target must live under the allowed
    # host-mount root (Docker) or the real home dir (bare-metal), never an
    # arbitrary filesystem path outside what this process should see.
    allowed_root = (Path(settings.host_mount_path) if settings.host_home else Path.home()).resolve()
    try:
        target.resolve().relative_to(allowed_root)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"path outside allowed root: {target}") from None

    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"path not found in container: {target}")
    if not (target / ".claude").is_dir():
        raise HTTPException(status_code=400, detail=f"no .claude folder in {target}")
    added = registry_add(str(target))
    return {"path": str(target), "added": added}


@router.post("/repos")
async def add_repo_endpoint(payload: dict) -> dict:
    """Append a new repo path to the runtime registry. Accepts either a host
    path (auto-translated) or an explicit container path.
    """
    raw = (payload.get("path") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="missing 'path'")
    settings = get_settings()
    return await asyncio.to_thread(_add_repo_sync, raw, settings)


@router.delete("/repos/{repo_id}")
async def delete_repo_endpoint(repo_id: str) -> dict:
    """Remove a repo from the runtime registry. Env REPO_ROOTS entries are
    not removable via this endpoint (only .env.docker edits).
    """
    for p in all_repo_paths():
        if p.name == repo_id:
            removed = registry_remove(str(p))
            return {"removed": removed, "path": str(p)}
    raise HTTPException(status_code=404, detail=f"repo not in registry: {repo_id}")
