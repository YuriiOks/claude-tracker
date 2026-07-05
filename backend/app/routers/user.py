"""User identity surfaced in the sidebar footer.

Reads what we can from the local environment:
- name / email: from git global config (best signal of "who's running this")
- claudeVersion: latest `version` field across recent JSONL transcripts
- initials: derived from name
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["user"])


def _git_config(key: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "config", "--global", key],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            v = r.stdout.strip()
            return v or None
    except Exception:
        pass
    return None


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _latest_claude_version() -> str | None:
    """Scan up to 6 most-recent JSONL files; return the highest `version`
    value found. None if no version field exists in any file."""
    settings = get_settings()
    projects = settings.projects_dir
    if not projects.is_dir():
        return None
    # Collect newest JSONL files across all project subdirs
    files: list[Path] = []
    for child in projects.iterdir():
        if child.is_dir():
            files.extend(child.glob("*.jsonl"))
    files.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)
    versions: set[str] = set()
    for jsonl in files[:6]:
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i > 50:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        v = json.loads(line).get("version")
                    except Exception:
                        continue
                    if isinstance(v, str) and v:
                        versions.add(v)
        except OSError:
            continue
    if not versions:
        return None
    # Sort by parsed semver tuple, take highest.
    def _parse(v: str) -> tuple:
        try:
            return tuple(int(x) for x in v.split(".") if x.isdigit())
        except Exception:
            return ()
    return max(versions, key=_parse)


@router.get("/user")
async def get_user() -> dict:
    """Returns ONLY fields the backend can discover reliably. Frontend merges
    with the mock USER for the rest (name, email, initials)."""
    return {
        "claudeVersion": _latest_claude_version(),
    }
