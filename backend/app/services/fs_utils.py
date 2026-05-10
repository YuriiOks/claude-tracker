"""Tiny filesystem helpers shared across services."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


def list_md_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def list_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in suffixes)


def read_frontmatter(path: Path) -> dict:
    try:
        post = frontmatter.load(path)
        return dict(post.metadata)
    except Exception as e:  # pragma: no cover
        logger.debug("frontmatter parse failed for %s: %s", path, e)
        return {}


def git_branch(repo_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "main"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"
