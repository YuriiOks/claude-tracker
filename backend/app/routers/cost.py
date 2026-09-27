"""GET /api/cost — rolled-up totals + per-day breakdown.

Totals here must reconcile exactly with /api/stats/dashboard's cost/tokens
figures for the same window: SessionSummaryRow is windowed by
`window_predicate` (last-event-attributed, same as stats.py and
repo_stats.py), not by `started_at` alone -- otherwise a long-running
session started outside the window but still updating inside it would be
counted on the dashboard and silently dropped here. SubagentCallRow has no
last-event timestamp of its own (calls are short-lived), so it stays
windowed by `started_at`, exactly like stats.py.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

import app.db as db_mod
from app.models.session_summary import SessionSummaryRow
from app.models.subagent_call import SubagentCallRow
from app.services.repo_registry import all_repo_paths
from app.services.stats_window import window_predicate

router = APIRouter(tags=["cost"])


@router.get("/cost")
async def get_cost(days: int = Query(default=7, ge=1, le=3650)) -> dict:
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    async with sm() as session:
        # Filter in SQL rather than pulling entire tables into memory. Same
        # window rule /api/stats/dashboard uses for SessionSummaryRow
        # (window_predicate: last_event_at, falling back to started_at).
        rows = (await session.execute(
            select(SessionSummaryRow).where(window_predicate(cutoff))
        )).scalars().all()
        sc_rows = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.started_at >= cutoff)
        )).scalars().all()

    # Untracked projects (any Claude Code project directory outside the
    # registered repo list) are still real spend and included in byRepo --
    # `tracked` just lets the frontend distinguish them, e.g. to still
    # reconcile a "tracked repos only" view against this endpoint's total.
    tracked_names = {p.name for p in all_repo_paths()}

    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
    by_repo: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
    by_agent: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    total_tokens = 0
    total_cost = 0.0

    for r in rows:
        ts = r.started_at if r.started_at.tzinfo else r.started_at.replace(tzinfo=UTC)
        day = ts.date().isoformat()
        by_day[day]["tokens"] += r.tokens
        by_day[day]["cost"] += r.cost
        by_repo[r.repo]["tokens"] += r.tokens
        by_repo[r.repo]["cost"] += r.cost
        total_tokens += r.tokens
        total_cost += r.cost

    for sc in sc_rows:
        ts = sc.started_at if sc.started_at.tzinfo else sc.started_at.replace(tzinfo=UTC)
        # Direct + workflow subagent spend is real spend -- fold it into the
        # same totals/byDay/byRepo breakdowns as main-session rows, not just
        # byAgent (previously the only place subagent spend showed up at
        # all, silently missing it from totalTokens/totalCost/byDay/byRepo).
        day = ts.date().isoformat()
        by_day[day]["tokens"] += sc.tokens
        by_day[day]["cost"] += sc.cost
        by_repo[sc.repo]["tokens"] += sc.tokens
        by_repo[sc.repo]["cost"] += sc.cost
        total_tokens += sc.tokens
        total_cost += sc.cost
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
            {
                "repo": k,
                "tokens": v["tokens"],
                "cost": round(v["cost"], 2),
                "tracked": k in tracked_names,
            }
            for k, v in sorted(by_repo.items(), key=lambda kv: -kv[1]["cost"])
        ],
        "byAgent": [
            {"agent": k, "calls": v["calls"], "tokens": v["tokens"], "cost": round(v["cost"], 2)}
            for k, v in sorted(by_agent.items(), key=lambda kv: -kv[1]["cost"])
        ],
    }
