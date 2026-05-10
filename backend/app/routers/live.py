"""Live event endpoints — REST cold-start (/api/live/recent) + WS (/ws/live)."""
from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.schemas.event import LiveEvent
from app.services.ingest import fetch_recent_events
from app.services.jsonl_parser import ParsedEvent
from app.services.live_stream import get_hub

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live"])


@router.get("/api/live/recent", response_model=list[LiveEvent])
async def recent(n: int = 60) -> list[LiveEvent]:
    rows = await fetch_recent_events(limit=n)
    if not rows:
        return []
    now = datetime.now(tz=UTC)
    out: list[LiveEvent] = []
    for r in rows:
        ts = r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=UTC)
        delta_s = int((ts - now).total_seconds())
        payload = json.loads(r.payload) if r.payload else {}
        out.append(LiveEvent(t=delta_s, repo=r.repo, kind=r.kind, **payload))
    return out


def _event_to_wire(ev: ParsedEvent) -> dict:
    now = datetime.now(tz=UTC)
    ts = ev.ts if ev.ts.tzinfo else ev.ts.replace(tzinfo=UTC)
    return {
        "t": int((ts - now).total_seconds()),
        "repo": ev.repo,
        "kind": ev.kind,
        **ev.payload,
    }


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    hub = get_hub()
    queue = await hub.subscribe()
    logger.info("ws/live subscriber connected (total=%d)", hub.subscribers)
    try:
        while True:
            ev = await queue.get()
            await ws.send_json(_event_to_wire(ev))
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("ws/live error: %s", e)
    finally:
        await hub.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await ws.close()
