from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.session import Session
from app.services.duration import fmt_duration, fmt_started
from app.services.ingest import fetch_recent_summaries

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[Session])
async def list_sessions(repo: str | None = None, limit: int = 50) -> list[Session]:
    rows = await fetch_recent_summaries(repo=repo, limit=limit)
    now = datetime.now(tz=timezone.utc)
    out: list[Session] = []
    for r in rows:
        started = r.started_at if r.started_at.tzinfo else r.started_at.replace(tzinfo=timezone.utc)
        last = r.last_event_at if r.last_event_at.tzinfo else r.last_event_at.replace(tzinfo=timezone.utc)
        out.append(
            Session(
                id=r.session_id[:8],
                repo=r.repo,
                started=fmt_started(started, now),
                duration="running" if r.status == "running" else fmt_duration(started, last),
                agent=r.agent or "",
                task=r.task or "",
                status=r.status,  # type: ignore[arg-type]
                tokens=r.tokens,
                cost=round(r.cost, 2),
                edits=r.edits,
            )
        )
    return out
