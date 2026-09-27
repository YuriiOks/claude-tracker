"""GET /api/auth/status (open) and GET /api/auth/pairing (trusted-local only).

Lets the frontend discover whether it needs to prompt for/store a token
before hitting a gated route, and lets a trusted-local session (the owner,
at the machine) fetch the token once to hand to another device (the phone).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas.auth import AuthPairing, AuthStatus
from app.security import TOKEN_HEADER, TOKEN_QUERY, check_token, get_token, is_trusted_local

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _request_token(request: Request) -> str | None:
    return request.headers.get(TOKEN_HEADER) or request.query_params.get(TOKEN_QUERY)


@router.get("/status", response_model=AuthStatus)
async def auth_status(request: Request) -> AuthStatus:
    trusted = is_trusted_local(request.headers.get("host", ""), request.headers.get("origin"))
    authenticated = trusted or check_token(_request_token(request))
    return AuthStatus(auth_required=not trusted, authenticated=authenticated)


@router.get("/pairing", response_model=AuthPairing)
async def auth_pairing(request: Request) -> AuthPairing:
    trusted = is_trusted_local(request.headers.get("host", ""), request.headers.get("origin"))
    if not trusted:
        raise HTTPException(status_code=403, detail="trusted-local only")
    return AuthPairing(token=get_token())
