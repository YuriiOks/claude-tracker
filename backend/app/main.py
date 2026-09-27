"""FastAPI factory."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.db import init_db
from app.security import SecurityMiddleware

logger = logging.getLogger(__name__)

# Safety-net full-corpus sweep interval -- with per-file byte-offset cursors
# (app.models.ingest_file_state) a no-op sweep costs a stat() per file, not a
# re-parse, so this only exists to catch anything the event-driven signal
# below missed (process restart before the watcher seeded, a change the
# watcher's debounce coalesced oddly, etc.), not to drive normal freshness.
INGEST_SWEEP_SEC = 60
# How long to wait after the FIRST queued change before running a tick, so a
# burst of writes to the same/related files (a session mid-turn touches its
# own file several times in quick succession) becomes one ingest call
# instead of one per change.
INGEST_DEBOUNCE_SEC = 1.0


async def _next_ingest_batch(queue: asyncio.Queue[Path], max_wait: float) -> set[Path] | None:
    """Wait up to `max_wait` seconds for the watcher to signal a change.

    Returns the debounced set of changed paths when at least one arrived in
    time, or None if the wait elapsed first (the caller should fall back to
    a since_hours safety sweep). `max_wait <= 0` means "the sweep deadline
    has already passed" -- go straight to the sweep without waiting at all.
    """
    if max_wait <= 0:
        return None
    try:
        first = await asyncio.wait_for(queue.get(), timeout=max_wait)
    except TimeoutError:
        return None
    pending = {first}
    await asyncio.sleep(INGEST_DEBOUNCE_SEC)
    while True:
        try:
            pending.add(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return pending


async def _ingest_loop(queue: asyncio.Queue[Path] | None = None):
    """Run a one-time full bootstrap ingest, then react to the live_stream
    watcher's change signal (near-instant freshness) with a periodic
    since_hours safety sweep as a fallback that fires on its own fixed
    cadence (INGEST_SWEEP_SEC) regardless of how much event-driven traffic
    is in between -- a continuous stream of changes must not starve the
    sweep, since the sweep is what catches anything the event-driven path
    itself missed (e.g. a watcher restart before it re-seeds). The bootstrap
    lives here (not in `lifespan`) so the app can start serving requests —
    including /api/health — immediately instead of blocking startup on a
    full-corpus walk. Bootstrap, the event-driven ticks, and the safety
    sweep all share this single task/coroutine, so exactly one ingest write
    is ever in flight. Logs and continues on error so a transient parse
    failure doesn't kill the loop.

    `queue` defaults to the live_stream module's global signal queue; tests
    can inject their own to avoid sharing that process-wide singleton.
    """
    from app.services.ingest import ingest_all

    if queue is None:
        from app.services.live_stream import get_ingest_signal_queue
        queue = get_ingest_signal_queue()

    try:
        r = await ingest_all()
        logger.info("bootstrap ingest: %s new, %s updated, %s events",
                    r.get("new"), r.get("updated"), r.get("events"))
    except Exception as e:  # noqa: BLE001
        logger.warning("bootstrap ingest failed: %s", e)

    next_sweep_at = time.monotonic() + INGEST_SWEEP_SEC
    while True:
        pending = await _next_ingest_batch(queue, next_sweep_at - time.monotonic())
        if pending is None:
            next_sweep_at = time.monotonic() + INGEST_SWEEP_SEC
        try:
            if pending:
                r = await ingest_all(changed_paths=pending)
                logger.info(
                    "ingest tick (event-driven, %d path(s)): new=%s updated=%s skipped=%s "
                    "events=%s in %ss",
                    len(pending), r.get("new"), r.get("updated"),
                    r.get("skipped"), r.get("events"), r.get("elapsed_s"),
                )
            else:
                r = await ingest_all(since_hours=24)
                logger.info(
                    "ingest tick (sweep): new=%s updated=%s skipped=%s events=%s in %ss",
                    r.get("new"), r.get("updated"),
                    r.get("skipped"), r.get("events"), r.get("elapsed_s"),
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("ingest tick failed: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    from app.services.live_stream import start_watcher, stop_watcher

    await start_watcher()
    ingest_task = asyncio.create_task(_ingest_loop())
    logger.info("claude-tracker backend started")
    try:
        yield
    finally:
        ingest_task.cancel()
        try:
            # Bound the wait — a long synchronous parse inside the ingest
            # loop won't observe cancellation until its next await point, so
            # an unbounded `await ingest_task` here can stall graceful
            # shutdown indefinitely. Abandon the task after a grace period
            # instead of blocking process exit on it.
            await asyncio.wait_for(ingest_task, timeout=5)
        except TimeoutError:
            logger.warning("ingest task did not stop within 5s; abandoning it")
        except (asyncio.CancelledError, Exception):
            pass
        await stop_watcher()
        logger.info("claude-tracker backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="claude-tracker",
        version="0.1.0",
        description="Local backend for the Claude Tracker dashboard.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added after CORS so it ends up outermost (Starlette's add_middleware
    # prepends) — it compresses the final HTTP response body including any
    # CORS headers already set. GZipMiddleware only intercepts scope["type"]
    # == "http", so /ws/live WebSocket traffic passes through untouched.
    app.add_middleware(GZipMiddleware, minimum_size=500)
    # Added last so it ends up outermost of all — auth/origin checks run
    # before GZip or CORS see the request at all. Handles both "http" and
    # "websocket" scopes (see app/security.py).
    app.add_middleware(SecurityMiddleware)

    # Routers
    from app.routers import (
        agents,
        auth,
        cost,
        diffs,
        files,
        health,
        integrations,
        live,
        live_agents,
        otel_ingest,
        permissions,
        plugins,
        repos,
        sessions,
        stats,
        telemetry,
        user,
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router)
    app.include_router(repos.router, prefix="/api")
    app.include_router(permissions.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(cost.router, prefix="/api")
    app.include_router(diffs.router, prefix="/api")
    app.include_router(integrations.router, prefix="/api")
    app.include_router(live_agents.router, prefix="/api")
    app.include_router(user.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(telemetry.router, prefix="/api")
    app.include_router(live.router)         # live.py declares full paths (/api + /ws)
    app.include_router(otel_ingest.router)  # full paths: /v1/logs, /v1/metrics

    return app


app = create_app()
