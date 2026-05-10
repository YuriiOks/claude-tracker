"""GET /api/agents — agent inventory + delegate edges from cached events."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

import app.db as db_mod
from app.config import get_settings
from app.models.session_event import LiveEventRow
from app.models.session_summary import SessionSummaryRow
from app.schemas.agent import AgentMeta
from app.services.fs_utils import read_frontmatter

router = APIRouter(tags=["agents"])


def _scan_agent_meta() -> dict[str, dict]:
    settings = get_settings()
    out: dict[str, dict] = {}
    sources = [(settings.claude_dir, "global")]
    sources.extend((p / ".claude", p.name) for p in settings.repo_paths)
    for claude_dir, scope in sources:
        agents_dir = claude_dir / "agents"
        if not agents_dir.is_dir():
            continue
        for path in agents_dir.rglob("*.md"):
            meta = read_frontmatter(path)
            name = path.stem
            if name in out:
                continue
            tools = meta.get("tools") or []
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",") if t.strip()]
            out[name] = {
                "repo": scope,
                "role": str(meta.get("description") or meta.get("role") or "")[:200],
                "tools": tools,
                "delegates": [],
                "callsToday": 0,
                "avgTokens": 0,
            }
    return out


@router.get("/agents", response_model=dict[str, AgentMeta])
async def list_agents() -> dict[str, AgentMeta]:
    meta = _scan_agent_meta()
    db_mod._ensure_engine()
    sm = db_mod._sessionmaker
    assert sm is not None

    delegate_map: dict[str, set[str]] = defaultdict(set)
    calls_today: Counter[str] = Counter()
    tokens_per_agent: dict[str, list[int]] = defaultdict(list)

    async with sm() as session:
        rows = (await session.execute(select(LiveEventRow))).scalars().all()
        for ev in rows:
            payload = json.loads(ev.payload) if ev.payload else {}
            if ev.kind == "delegate":
                src = payload.get("from", "main")
                tgt = payload.get("to", "")
                if tgt:
                    delegate_map[src].add(tgt)
        today = datetime.now(tz=timezone.utc).date()
        summaries = (await session.execute(select(SessionSummaryRow))).scalars().all()
        for s in summaries:
            ts = s.started_at if s.started_at.tzinfo else s.started_at.replace(tzinfo=timezone.utc)
            if ts.date() == today and s.agent:
                calls_today[s.agent] += 1
                tokens_per_agent[s.agent].append(s.tokens)

    for name, m in meta.items():
        m["delegates"] = sorted(delegate_map.get(name, set()))
        m["callsToday"] = calls_today.get(name, 0)
        toks = tokens_per_agent.get(name, [])
        m["avgTokens"] = int(sum(toks) / len(toks)) if toks else 0

    return {name: AgentMeta.model_validate(m) for name, m in meta.items()}


@router.get("/agents/{name}", response_model=AgentMeta)
async def get_agent(name: str) -> AgentMeta:
    all_meta = await list_agents()
    if name not in all_meta:
        raise HTTPException(404, f"agent not found: {name}")
    return all_meta[name]
