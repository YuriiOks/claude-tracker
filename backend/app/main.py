"""FastAPI factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    from app.services.live_stream import start_watcher, stop_watcher

    await start_watcher()
    logger.info("claude-tracker backend started")
    try:
        yield
    finally:
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

    # Routers
    from app.routers import agents, cost, diffs, health, integrations, live, permissions, plugins, repos, sessions
    app.include_router(health.router, prefix="/api")
    app.include_router(repos.router, prefix="/api")
    app.include_router(permissions.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(cost.router, prefix="/api")
    app.include_router(diffs.router, prefix="/api")
    app.include_router(integrations.router, prefix="/api")
    app.include_router(live.router)  # live.py declares full paths (/api + /ws)

    return app


app = create_app()
