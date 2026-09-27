from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.schemas.session import Session
from app.services.duration import fmt_duration, fmt_started
from app.services.ingest import fetch_recent_summaries, fetch_subagent_totals

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[Session])
async def list_sessions(
    repo: str | None = None, limit: int = Query(default=50, ge=1, le=500)
) -> list[Session]:
    rows = await fetch_recent_summaries(repo=repo, limit=limit)
    # A session's total must include what its direct + workflow subagents
    # spent -- they're not sessions of their own, their spend belongs here.
    sub_totals = await fetch_subagent_totals([r.session_id for r in rows])
    now = datetime.now(tz=UTC)
    out: list[Session] = []
    for r in rows:
        started = r.started_at if r.started_at.tzinfo else r.started_at.replace(tzinfo=UTC)
        last = r.last_event_at if r.last_event_at.tzinfo else r.last_event_at.replace(tzinfo=UTC)
        sub_tokens, sub_cost = sub_totals.get(r.session_id, (0, 0.0))
        out.append(
            Session(
                id=r.session_id[:8],
                repo=r.repo,
                started=fmt_started(started, now),
                duration="running" if r.status == "running" else fmt_duration(started, last),
                agent=r.agent or "",
                task=r.task or "",
                status=r.status,  # type: ignore[arg-type]
                tokens=r.tokens + sub_tokens,
                cost=round(r.cost + sub_cost, 2),
                edits=r.edits,
            )
        )
    return out
