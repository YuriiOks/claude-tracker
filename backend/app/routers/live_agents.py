"""GET /api/live/agents — sessions Claude Code is currently working on."""
from __future__ import annotations

from fastapi import APIRouter

from app.services.live_agents import get_tracker

router = APIRouter(tags=["live"])


@router.get("/live/agents")
async def active_agents() -> list[dict]:
    return await get_tracker().snapshot()
