"""GET /api/auth/status (open) and GET /api/auth/pairing (trusted-local only).

Lets the frontend discover whether it needs to prompt for/store a token
before hitting a gated route, and lets a trusted-local session (the owner,
at the machine) fetch the token once to hand to another device (the phone).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.schemas.auth import AuthPairing, AuthStatus
from app.security import TOKEN_HEADER, TOKEN_QUERY, check_token, get_token, is_trusted_local

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _request_token(request: Request) -> str | None:
    return request.headers.get(TOKEN_HEADER) or request.query_params.get(TOKEN_QUERY)


def _trusted_local(request: Request) -> bool:
    """Host-based trust, disabled outright in LAN mode (see app.security)."""
    if get_settings().lan_mode:
        return False
    return is_trusted_local(request.headers.get("host", ""), request.headers.get("origin"))


@router.get("/status", response_model=AuthStatus)
async def auth_status(request: Request) -> AuthStatus:
    trusted = _trusted_local(request)
    authenticated = trusted or check_token(_request_token(request))
    return AuthStatus(auth_required=not trusted, authenticated=authenticated)


@router.get("/pairing", response_model=AuthPairing)
async def auth_pairing(request: Request) -> AuthPairing:
    """Trusted-local only -- and impossible in LAN mode.

    LAN mode turns off Host-based trust precisely because it can't be
    trusted over HTTP (a LAN client can forge `Host: localhost`), so this
    endpoint can't safely mint a token here either. Pairing instead happens
    out-of-band via `tracker pair` / `make pair` on the host (app.cli).
    """
    if get_settings().lan_mode:
        raise HTTPException(status_code=403, detail="pairing unavailable in LAN mode — run `make pair`")
    if not _trusted_local(request):
        raise HTTPException(status_code=403, detail="trusted-local only")
    return AuthPairing(token=get_token())
