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


def _set_lan_mode(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    from app import config

    monkeypatch.setenv("LAN_MODE", "1" if value else "0")
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


# ─── LAN_MODE ──────────────────────────────────────────────────────────────
# LAN_MODE turns off Host-based trust entirely (see app.security module
# docstring) -- a localhost Host header is no longer special, even though
# every test above still uses one to get the default trusted-local pass.
# These tests exercise the same localhost Host with LAN_MODE on instead, plus
# the /v1/* peer-address exception.

@pytest.mark.asyncio
async def test_lan_mode_localhost_host_without_token_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/repos")
    assert res.status_code == 401
    assert res.json() == {"detail": "auth required"}


@pytest.mark.asyncio
async def test_lan_mode_localhost_host_with_token_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    _set_token(monkeypatch, "lan-secret")
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        no_token = await c.get("/api/repos")
        assert no_token.status_code == 401

        res = await c.get("/api/repos", headers={"X-Tracker-Token": "lan-secret"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lan_mode_pairing_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/auth/pairing")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_lan_mode_health_still_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


@pytest.mark.asyncio
async def test_lan_mode_auth_status_reports_localhost_as_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json() == {"authRequired": True, "authenticated": False}


# ─── LAN_MODE /v1 exception ─────────────────────────────────────────────────
# /v1/* (OTel ingest) is trusted by ASGI peer address instead of Host header
# even in LAN mode -- see _is_trusted_v1_peer's docstring for why that's safe
# (the backend port is never LAN-published, and neither the Vite proxy nor
# nginx forwards /v1/*, so only loopback/Docker-bridge peers can ever reach
# it regardless of this check).

_OTLP_EMPTY_LOGS = {"resourceLogs": []}


@pytest.mark.asyncio
async def test_lan_mode_v1_trusted_from_loopback_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.post("/v1/logs", json=_OTLP_EMPTY_LOGS)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lan_mode_v1_trusted_from_docker_bridge_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_lan_mode(monkeypatch, True)
    from app.main import create_app

    app = create_app()
    # The compose network gateway -- where host-originated traffic to the
    # published port arrives from. Observed on the owner's Mac: 192.168.48.1
    # on 192.168.48.0/20 (not 172.16/12), so the attached networks are
    # detected from /proc/net/route rather than hardcoded.
    import ipaddress

    from app import security

    monkeypatch.setattr(
        security, "_attached_networks", lambda: (ipaddress.ip_network("192.168.48.0/20"),)
    )
    transport = httpx.ASGITransport(app=app, client=("192.168.48.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        res = await c.post("/v1/logs", json=_OTLP_EMPTY_LOGS)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lan_mode_v1_rejects_real_lan_peer_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_lan_mode(monkeypatch, True)
    _set_token(monkeypatch, "lan-secret")
    from app.main import create_app

    app = create_app()
    # A genuine LAN address (outside both loopback and the Docker bridge
    # range) must NOT get the /v1 peer-address exception.
    transport = httpx.ASGITransport(app=app, client=("192.168.1.50", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        no_token = await c.post("/v1/logs", json=_OTLP_EMPTY_LOGS)
        assert no_token.status_code == 401

        with_token = await c.post(
            "/v1/logs", json=_OTLP_EMPTY_LOGS, headers={"X-Tracker-Token": "lan-secret"}
        )
    assert with_token.status_code == 200


def test_parse_proc_net_route_returns_on_link_networks_only() -> None:
    # Exact /proc/net/route captured from the owner's backend container.
    import ipaddress

    from app.security import _parse_proc_net_route

    text = (
        "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t0130A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
        "eth0\t0030A8C0\t00000000\t0001\t0\t0\t0\t00F0FFFF\t0\t0\t0\n"
    )
    assert _parse_proc_net_route(text) == [ipaddress.ip_network("192.168.48.0/20")]
