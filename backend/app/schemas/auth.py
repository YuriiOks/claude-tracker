"""Response models for the auth status/pairing endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class AuthStatus(_CamelModel):
    """GET /api/auth/status — always open, cross-origin checked only."""
    auth_required: bool
    authenticated: bool


class AuthPairing(_CamelModel):
    """GET /api/auth/pairing — trusted-local only, else 403."""
    token: str
