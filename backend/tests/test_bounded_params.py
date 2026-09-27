"""R-SEC-9: pagination-style query params must reject out-of-range values
instead of allowing an unbounded/negative table scan."""
from __future__ import annotations

import httpx
import pytest


@pytest.fixture
async def client():
    """Fresh DB per test -- these routes all call db_mod._ensure_engine(),
    which no-ops if a prior test already populated the module-level engine
    globals for a different (possibly now-deleted) tmp DB path."""
    import app.db as db_mod
    db_mod._engine = None
    db_mod._sessionmaker = None
    await db_mod.init_db()

    from app.main import create_app
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_sessions_limit_negative_422(client):
    r = await client.get("/api/sessions?limit=-1")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sessions_limit_valid_200(client):
    r = await client.get("/api/sessions?limit=10")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_live_recent_n_negative_422(client):
    r = await client.get("/api/live/recent?n=-5")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_live_recent_n_valid_200(client):
    r = await client.get("/api/live/recent?n=10")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cost_days_negative_422(client):
    r = await client.get("/api/cost?days=-7")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_cost_days_valid_200(client):
    r = await client.get("/api/cost?days=7")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cost_days_over_cap_422(client):
    r = await client.get("/api/cost?days=999999")
    assert r.status_code == 422
