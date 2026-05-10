from fastapi import APIRouter, HTTPException

from app.schemas.inventory import GlobalEnvelope
from app.schemas.repo import Repo
from app.services.repo_scanner import get_repo_by_id, scan_all_repos, scan_global

router = APIRouter(prefix="", tags=["repos"])


@router.get("/repos", response_model=list[Repo])
async def list_repos() -> list[Repo]:
    return scan_all_repos()


@router.get("/repos/{repo_id}", response_model=Repo)
async def get_repo(repo_id: str) -> Repo:
    repo = get_repo_by_id(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"repo not found: {repo_id}")
    return repo


@router.get("/global", response_model=GlobalEnvelope)
async def get_global() -> GlobalEnvelope:
    return scan_global()
