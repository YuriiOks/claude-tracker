"""R-BE-38: GZipMiddleware compresses large responses without breaking CORS."""
from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_openapi_response_is_gzip_compressed() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        res = await client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert res.status_code == 200
    assert res.headers.get("content-encoding") == "gzip"
    # httpx transparently decodes the body — it must still be valid JSON.
    assert "paths" in res.json()


@pytest.mark.asyncio
async def test_small_response_is_not_gzip_compressed() -> None:
    """/api/health is well under minimum_size=500 — GZip must leave it alone."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        res = await client.get("/api/health", headers={"Accept-Encoding": "gzip"})

    assert res.status_code == 200
    assert "content-encoding" not in res.headers
