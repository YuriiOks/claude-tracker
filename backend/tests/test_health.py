from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
