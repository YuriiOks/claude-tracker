"""GET /api/live/recent — last N events from cache (cold-start data for the WS)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.event import LiveEvent
from app.services.ingest import fetch_recent_events

router = APIRouter(tags=["live"])


@router.get("/live/recent", response_model=list[LiveEvent])
async def recent(n: int = 60) -> list[LiveEvent]:
    rows = await fetch_recent_events(limit=n)
    if not rows:
        return []
    now = datetime.now(tz=timezone.utc)
    out: list[LiveEvent] = []
    for r in rows:
        ts = r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=timezone.utc)
        delta_s = int((ts - now).total_seconds())  # negative for past events
        payload = json.loads(r.payload) if r.payload else {}
        out.append(LiveEvent(t=delta_s, repo=r.repo, kind=r.kind, **payload))
    return out
