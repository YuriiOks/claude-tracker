from fastapi import APIRouter, HTTPException

from app.schemas.inventory import GlobalEnvelope
from app.schemas.repo import Repo
from app.services.repo_scanner import scan_all_repos, scan_global

router = APIRouter(prefix="", tags=["repos"])


@router.get("/repos", response_model=list[Repo])
async def list_repos() -> list[Repo]:
    return scan_all_repos()


@router.get("/repos/{repo_id}", response_model=Repo)
async def get_repo(repo_id: str) -> Repo:
    for repo in scan_all_repos():
        if repo.id == repo_id:
            return repo
    raise HTTPException(status_code=404, detail=f"repo not found: {repo_id}")


@router.get("/global", response_model=GlobalEnvelope)
async def get_global() -> GlobalEnvelope:
    return scan_global()
