"""Auth + Origin/Host gate for the single-user local dashboard.

Threat model: a phone on the home LAN is a wanted client (via the Vite proxy
or the docker/nginx frontend port); every *other* device on the LAN, and any
tab already open in a browser on the host, is not. Two independent checks:

1. Trusted-local passthrough. If the Host header resolves to localhost /
   127.0.0.1 / ::1 (and any Origin header does too), no token is required —
   this is "the owner, on the machine". Everything else needs the shared
   token, issued once and persisted at <DB_PATH's directory>/auth-token
   (mode 0600), sent as the `X-Tracker-Token` header, or `?token=` for
   WebSockets (browsers cannot set arbitrary headers on a WS handshake).

2. Cross-origin block, applied to every request regardless of (1). If an
   Origin header is present and its host:port doesn't match the Host
   header's host:port, the request is rejected outright. This is the
   DNS-rebinding / CSRF defence: an attacker-controlled hostname that
   resolves to 127.0.0.1 still sends its own Origin, which won't match.

Both the Vite dev proxy (changeOrigin: false) and nginx (`Host $http_host`)
forward the browser's *original* Host, so a legitimate same-origin request
via either proxy always has Host == Origin's authority — only a request
that bypasses the proxy (or forges an Origin) trips this check.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger(__name__)

TOKEN_HEADER = "x-tracker-token"
TOKEN_QUERY = "token"

_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

# Paths the middleware never gates (no token, ever) — /api/health for the
# Docker healthcheck, /api/auth/status so the frontend can ask "do I need a
# token?" without already having one. /api/auth/pairing is deliberately NOT
# here: it has its own trusted-local-only rule (see app.routers.auth), which
# is stricter than "trusted-local or token", so it must not fall through to
# the generic token check below.
OPEN_PATHS = {"/api/health", "/api/auth/status"}
UNGATED_PATHS = OPEN_PATHS | {"/api/auth/pairing"}

# Prefixes that require the trusted-local-or-token gate at all. Static
# assets, /docs, /openapi.json etc. are left alone (still subject to the
# cross-origin check below, for whatever that's worth on a GET-only asset).
_GATED_PREFIXES = ("/api/", "/ws/", "/v1/")
_GATED_EXACT = {"/api", "/ws"}


def _token_path(settings) -> Path:  # noqa: ANN001
    return settings.db_path.parent / "auth-token"


def get_token() -> str:
    """Return the shared auth token, generating + persisting it on first use.

    `TRACKER_TOKEN` (via Settings) overrides and is never written to disk by
    us. The generated token is never logged.
    """
    settings = get_settings()
    if settings.tracker_token:
        return settings.tracker_token

    path = _token_path(settings)
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    os.chmod(path, 0o600)
    return token


def check_token(provided: str | None) -> bool:
    """Constant-time compare `provided` against the current shared token."""
    if not provided:
        return False
    return hmac.compare_digest(provided, get_token())


def _split_host_port(value: str) -> tuple[str, str | None]:
    """Split a Host-header-style 'host[:port]' value (handles bracketed IPv6)."""
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            host = value[1:end]
            rest = value[end + 1 :]
            port = rest[1:] if rest.startswith(":") else None
            return host.lower(), port
    if value.count(":") == 1:
        host, _, port = value.partition(":")
        return host.lower(), port or None
    return value.lower(), None


def _origin_host_port(origin: str) -> tuple[str, str | None] | None:
    """Parse an Origin header into (host, port). None if unparseable — e.g.
    the literal 'null' origin sandboxed/file contexts send."""
    if not origin or origin == "null":
        return None
    parts = urlsplit(origin)
    if not parts.hostname:
        return None
    return parts.hostname.lower(), (str(parts.port) if parts.port else None)


def is_trusted_local(host_header: str, origin_header: str | None) -> bool:
    """Host resolves to a local hostname AND (no Origin, or Origin does too)."""
    host, _ = _split_host_port(host_header or "")
    if host not in _LOCAL_HOSTNAMES:
        return False
    if not origin_header:
        return True
    parsed = _origin_host_port(origin_header)
    if parsed is None:
        return False
    origin_host, _ = parsed
    return origin_host in _LOCAL_HOSTNAMES


def is_cross_origin(host_header: str, origin_header: str | None) -> bool:
    """True if an Origin header is present and its host:port != Host's.

    A present-but-unparseable Origin ("null", malformed) fails closed —
    it can't be proven same-origin, so it's treated as cross-origin.
    """
    if not origin_header:
        return False
    parsed = _origin_host_port(origin_header)
    if parsed is None:
        return True
    host, port = _split_host_port(host_header or "")
    return parsed != (host, port)


def _extract_token(scope: Scope, headers: dict[bytes, bytes]) -> str | None:
    token = headers.get(TOKEN_HEADER.encode("latin-1"))
    if token:
        return token.decode("latin-1")
    if scope["type"] == "websocket":
        query = (scope.get("query_string") or b"").decode("latin-1")
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == TOKEN_QUERY and value:
                return value
    return None


class SecurityMiddleware:
    """Pure-ASGI middleware: cross-origin block + trusted-local-or-token gate.

    Runs for both `http` and `websocket` scopes so /ws/live gets the same
    protection as the REST routes. Rejections: 401/`4401` for a missing or
    invalid token, 403/`4403` for a cross-origin request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower().encode("latin-1"): v for k, v in scope.get("headers") or []}
        host_header = (headers.get(b"host") or b"").decode("latin-1")
        origin_header = (headers.get(b"origin") or b"").decode("latin-1") or None
        path = scope["path"]

        if is_cross_origin(host_header, origin_header):
            await self._reject(scope, receive, send, status=403, ws_code=4403,
                                detail="cross-origin request blocked")
            return

        if not (path in _GATED_EXACT or path.startswith(_GATED_PREFIXES)):
            await self.app(scope, receive, send)
            return

        if path in UNGATED_PATHS:
            await self.app(scope, receive, send)
            return

        if is_trusted_local(host_header, origin_header):
            await self.app(scope, receive, send)
            return

        if check_token(_extract_token(scope, headers)):
            await self.app(scope, receive, send)
            return

        await self._reject(scope, receive, send, status=401, ws_code=4401, detail="auth required")

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, *, status: int, ws_code: int, detail: str
    ) -> None:
        if scope["type"] == "websocket":
            # A custom close code is only visible to the client once the
            # handshake has completed — reject-before-accept collapses to a
            # generic 1006 on most clients, so accept then close.
            await receive()  # drain "websocket.connect"
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.close", "code": ws_code})
            return
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)
