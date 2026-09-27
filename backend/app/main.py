"""FastAPI factory."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.db import init_db
from app.security import SecurityMiddleware

logger = logging.getLogger(__name__)

# Re-ingest interval — keeps session_summary table fresh so /api/stats
# and /api/repos return today's numbers without manual `tracker ingest`.
INGEST_INTERVAL_SEC = 30


async def _ingest_loop():
    """Run a one-time full bootstrap ingest, then incremental ingest every
    INGEST_INTERVAL_SEC. The bootstrap lives here (not in `lifespan`) so the
    app can start serving requests — including /api/health — immediately
    instead of blocking startup on a full-corpus walk. Bootstrap and the
    periodic ticks share this single task/coroutine, so they never run
    concurrently. Logs and continues on error so a transient parse failure
    doesn't kill the loop."""
    from app.services.ingest import ingest_all

    try:
        r = await ingest_all()
        logger.info("bootstrap ingest: %s new, %s updated, %s events",
                    r.get("new"), r.get("updated"), r.get("events"))
    except Exception as e:  # noqa: BLE001
        logger.warning("bootstrap ingest failed: %s", e)

    while True:
        try:
            r = await ingest_all(since_hours=24)
            logger.info(
                "ingest tick: new=%s updated=%s skipped=%s events=%s in %ss",
                r.get("new"), r.get("updated"),
                r.get("skipped"), r.get("events"), r.get("elapsed_s"),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ingest tick failed: %s", e)
        await asyncio.sleep(INGEST_INTERVAL_SEC)


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
