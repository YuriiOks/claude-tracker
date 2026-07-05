"""GET /api/integrations/{repo_id} — Linear ticket + GitHub PR for a repo's branch."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.services.fs_utils import git_branch
from app.services.integrations import (
    github_pr_for_branch,
    langfuse_cost_for_session,
    linear_ticket_for_branch,
)
from app.services.repo_scanner import scan_all_repos

router = APIRouter(tags=["integrations"])


@router.get("/integrations/{repo_id}")
async def integrations_for_repo(repo_id: str) -> dict:
    repos = scan_all_repos()
    target = next((r for r in repos if r.id == repo_id), None)
    if target is None:
        raise HTTPException(404, f"repo not found: {repo_id}")
    # `path` is stored with leading ~ — expand to actual filesystem path for gh.
    from pathlib import Path

    repo_path = Path(target.path.replace("~", str(Path.home()), 1)).expanduser()
    branch = target.branch or await asyncio.to_thread(git_branch, repo_path)
    return {
        "repo": repo_id,
        "branch": branch,
        "linear": await linear_ticket_for_branch(branch),
        "githubPr": await asyncio.to_thread(github_pr_for_branch, repo_path, branch),
    }


@router.get("/integrations/cost/{session_id}")
async def langfuse_cost(session_id: str) -> dict:
    """Optional — fetches Langfuse-recorded totals for a single session."""
    return {"sessionId": session_id, "langfuse": await langfuse_cost_for_session(session_id)}
