"""GET /api/cost — rolled-up totals + per-day breakdown."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

import app.db as db_mod
from app.models.session_summary import SessionSummaryRow

router = APIRouter(tags=["cost"])


@router.get("/cost")
async def get_cost(days: int = 7) -> dict:
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    async with sm() as session:
        rows = (await session.execute(select(SessionSummaryRow))).scalars().all()

    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
    by_repo: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
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
    }
