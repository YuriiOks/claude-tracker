"""Tests for app.security: trusted-local bypass, LAN token gate,
cross-origin block, WS auth, and the auth status/pairing endpoints.

Every existing test in this suite builds its client with base_url set to a
local hostname (see conftest.py + the blanket http://test -> http://localhost
swap done alongside this file), so they all pass through as trusted-local
without needing a token. These tests are the ones that deliberately use a
non-local Host to exercise the gate itself.
"""
from __future__ import annotations

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

LAN_BASE_URL = "http://192.168.1.5:47820"


def _set_token(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    from app import config

    monkeypatch.setenv("TRACKER_TOKEN", token)
    config.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_trusted_local_passes_without_token() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/repos")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lan_host_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_token(monkeypatch, "s3cr3t-token")
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=LAN_BASE_URL) as c:
        no_token = await c.get("/api/repos")
        assert no_token.status_code == 401
        assert no_token.json() == {"detail": "auth required"}

        wrong_token = await c.get("/api/repos", headers={"X-Tracker-Token": "nope"})
        assert wrong_token.status_code == 401

        with_token = await c.get("/api/repos", headers={"X-Tracker-Token": "s3cr3t-token"})
        assert with_token.status_code == 200


@pytest.mark.asyncio
async def test_cross_origin_blocked_even_when_trusted_local() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/repos", headers={"Origin": "http://evil.example"})
    assert res.status_code == 403
    assert res.json() == {"detail": "cross-origin request blocked"}


@pytest.mark.asyncio
async def test_health_is_open_from_lan_host() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=LAN_BASE_URL) as c:
        res = await c.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


@pytest.mark.asyncio
async def test_auth_status_open_and_reports_lan_as_unauthenticated() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=LAN_BASE_URL) as c:
        res = await c.get("/api/auth/status")
    assert res.status_code == 200
    body = res.json()
    assert body == {"authRequired": True, "authenticated": False}


@pytest.mark.asyncio
async def test_auth_status_reports_trusted_local_as_authenticated() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/auth/status")
    assert res.status_code == 200
    body = res.json()
    assert body == {"authRequired": False, "authenticated": True}


@pytest.mark.asyncio
async def test_pairing_served_to_trusted_local_only() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        local = await c.get("/api/auth/pairing")
    assert local.status_code == 200
    assert "token" in local.json()

    async with httpx.AsyncClient(transport=transport, base_url=LAN_BASE_URL) as c:
        lan = await c.get("/api/auth/pairing")
    assert lan.status_code == 403


def test_ws_lan_without_token_closed_4401() -> None:
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    # NB: starlette's TestClient.websocket_connect always resolves the URL
    # against a hardcoded "ws://testserver" base regardless of the
    # TestClient's own `base_url` -- the only reliable way to simulate a LAN
    # Host header here is to set it explicitly.
    with (
        client.websocket_connect("/ws/live", headers={"host": "192.168.1.5:47820"}) as ws,
        pytest.raises(WebSocketDisconnect) as exc_info,
    ):
        ws.receive_text()
    assert exc_info.value.code == 4401


def test_ws_trusted_local_connects_without_token() -> None:
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    # No exception on connect -- the middleware lets it through to the
    # ws_live handler, which accepts and then just waits for events.
    with client.websocket_connect("/ws/live", headers={"host": "localhost"}):
        pass
