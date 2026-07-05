"""GET /api/cost — rolled-up totals + per-day breakdown."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

import app.db as db_mod
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow

router = APIRouter(tags=["cost"])


@router.get("/cost")
async def get_cost(days: int = 7) -> dict:
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    async with sm() as session:
        # Filter in SQL rather than pulling entire tables into memory.
        rows = (await session.execute(
            select(SessionSummaryRow).where(SessionSummaryRow.started_at >= cutoff)
        )).scalars().all()
        sc_rows = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.started_at >= cutoff)
        )).scalars().all()

    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
    by_repo: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
    by_agent: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    total_tokens = 0
    total_cost = 0.0

    for r in rows:
        ts = r.started_at if r.started_at.tzinfo else r.started_at.replace(tzinfo=UTC)
        if ts < cutoff:
            continue
        day = ts.date().isoformat()
        by_day[day]["tokens"] += r.tokens
        by_day[day]["cost"] += r.cost
        by_repo[r.repo]["tokens"] += r.tokens
        by_repo[r.repo]["cost"] += r.cost
        total_tokens += r.tokens
        total_cost += r.cost

    for sc in sc_rows:
        ts = sc.started_at if sc.started_at.tzinfo else sc.started_at.replace(tzinfo=UTC)
        if ts < cutoff:
            continue
        by_agent[sc.agent_type]["calls"] += 1
        by_agent[sc.agent_type]["tokens"] += sc.tokens
        by_agent[sc.agent_type]["cost"] += sc.cost

    return {
        "windowDays": days,
        "totalTokens": total_tokens,
        "totalCost": round(total_cost, 2),
        "byDay": [
            {"day": d, "tokens": v["tokens"], "cost": round(v["cost"], 2)}
            for d, v in sorted(by_day.items())
        ],
        "byRepo": [
            {"repo": k, "tokens": v["tokens"], "cost": round(v["cost"], 2)}
            for k, v in sorted(by_repo.items(), key=lambda kv: -kv[1]["cost"])
        ],
        "byAgent": [
            {"agent": k, "calls": v["calls"], "tokens": v["tokens"], "cost": round(v["cost"], 2)}
            for k, v in sorted(by_agent.items(), key=lambda kv: -kv[1]["cost"])
        ],
    }
