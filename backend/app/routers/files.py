"""Serve .md/.html file contents from tracked repos for the MarkdownPanel.

Path traversal is blocked — the resolved target must live inside the repo root.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.repo_registry import all_repo_paths

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["files"])

MAX_BYTES = 256 * 1024  # 256 KiB cap


def _resolve_repo(repo_id: str) -> Path:
    for p in all_repo_paths():
        if p.name == repo_id:
            return p
    raise HTTPException(status_code=404, detail=f"repo not found: {repo_id}")


# IMPORTANT: this route must be declared BEFORE the catch-all `{rel_path:path}`
# below — otherwise FastAPI matches the greedy version first.
def _list_files_in_dir(repo_root, dir_rel: str, ext: str):
    target_dir = (repo_root / dir_rel).resolve()
    # Path-traversal guard
    try:
        target_dir.relative_to(repo_root)
    except ValueError:
        return []
    if not target_dir.is_dir():
        return []
    ext = ext.lower().lstrip(".")
    out: list[dict] = []
    for f in target_dir.glob(f"*.{ext}"):
        try:
            st = f.stat()
            out.append({
                "path": str(f.relative_to(repo_root)),
                "name": f.stem,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
        except OSError:
            continue
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


@router.get("/repos/{repo_id}/artifacts/html")
async def list_html_artifacts(repo_id: str, dir: str = "docs") -> list[dict]:
    """List `.html` files in a tracked repo. Defaults to `docs/`; pass `?dir=`
    to scan another directory (e.g. `.claude/skills/html-docs/templates`)."""
    repo_root = _resolve_repo(repo_id).resolve()
    return _list_files_in_dir(repo_root, dir, ".html")


def _inline_css_imports(html: str, base_dir: Path, root: Path) -> str:
    """Replace `@import url("./xxx.css")` (and single-quoted/no-./variants)
    with the literal contents of the sibling .css file.

    Templates produced by the html-docs skill rely on a relative @import to
    pull in _tokens.css. That works when the file is opened from disk but
    NOT inside an iframe srcDoc (no base URL). We resolve those imports
    server-side so embedded previews render styled.
    """
    pattern = re.compile(r'@import\s+url\(\s*[\'"](\.?/?[^\'"\)]+\.css)[\'"]\s*\)\s*;?')
    def repl(match: re.Match) -> str:
        rel = match.group(1).lstrip('./')
        sibling = (base_dir / rel).resolve()
        try:
            sibling.relative_to(root)  # path-traversal guard
        except ValueError:
            return match.group(0)
        if not sibling.is_file() or sibling.suffix.lower() != ".css":
            return match.group(0)
        try:
            return sibling.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return match.group(0)
    return pattern.sub(repl, html)


@router.get("/files/{repo_id}/{rel_path:path}")
async def get_file(repo_id: str, rel_path: str) -> dict:
    repo_root = _resolve_repo(repo_id).resolve()
    target = (repo_root / rel_path).resolve()

    # Path-traversal guard
    try:
        target.relative_to(repo_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path outside repo") from None

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {rel_path}")

    # Whitelist text formats we render
    if target.suffix.lower() not in {".md", ".html", ".htm", ".json", ".sh", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".txt", ".yaml", ".yml", ".toml"}:
        raise HTTPException(status_code=415, detail=f"unsupported file type: {target.suffix}")

    size = target.stat().st_size
    if size > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"file too large ({size} bytes)")

    content = target.read_text(encoding="utf-8", errors="replace")
    # For HTML files, resolve any `@import url("./xxx.css")` references so
    # the file renders styled in an iframe srcDoc (no base URL there).
    if target.suffix.lower() in {".html", ".htm"}:
        content = _inline_css_imports(content, target.parent, repo_root)
    return {
        "repo": repo_id,
        "path": str(target.relative_to(repo_root)),
        "size": size,
        "content": content,
    }
