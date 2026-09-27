from __future__ import annotations

import asyncio
import time

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


@pytest.mark.asyncio
async def test_health_responds_promptly_during_slow_bootstrap_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-BE-01: the app must serve /api/health immediately at startup even
    when the full bootstrap ingest is slow — the bootstrap now runs as the
    first step of the background ingest loop, not as a blocking `lifespan`
    step before `yield`."""
    calls: list[object] = []

    async def _slow_ingest_all(*args, **kwargs):
        calls.append((args, kwargs))
        await asyncio.sleep(5)
        return {"new": 0, "updated": 0, "skipped": 0, "events": 0, "elapsed_s": 0}

    monkeypatch.setattr("app.services.ingest.ingest_all", _slow_ingest_all)

    from app.main import create_app

    app = create_app()
    started = time.monotonic()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            res = await asyncio.wait_for(client.get("/api/health"), timeout=1.0)
        elapsed = time.monotonic() - started
        # The ASGI request can complete without yielding to the event loop, so
        # give the background ingest task a chance to take its first step
        # before the lifespan exits (and cancels it).
        for _ in range(100):
            if calls:
                break
            await asyncio.sleep(0.01)

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    # Must not block on the 5s mocked bootstrap ingest.
    assert elapsed < 1.0
    # ... but the bootstrap must still have been kicked off in the background.
    assert calls, "bootstrap ingest was not invoked"
