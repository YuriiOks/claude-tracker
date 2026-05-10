from fastapi import APIRouter

from app.services.repo_scanner import collect_plugins_dict

router = APIRouter(tags=["plugins"])


@router.get("/plugins")
async def get_plugins() -> dict:
    return collect_plugins_dict()
