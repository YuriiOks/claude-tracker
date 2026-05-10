from fastapi import APIRouter

from app.schemas.inventory import PermissionsDetail
from app.services.repo_scanner import collect_permissions_detail

router = APIRouter(tags=["permissions"])


@router.get("/permissions", response_model=PermissionsDetail)
async def get_permissions() -> PermissionsDetail:
    return collect_permissions_detail()
