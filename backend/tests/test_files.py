"""R-BE-31: repo=global resolves to settings.claude_dir, accepting both
`agents/x.md` and `.claude/agents/x.md` (AgentDetail sends the latter for
repo-scoped agents). Traversal outside claude_dir must still be rejected.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest


@pytest.fixture
def claude_dir_with_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "claude"
    (fake / "agents").mkdir(parents=True)
    (fake / "agents" / "x.md").write_text("hello agent")
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "claude_dir", fake)
    return fake


@pytest.mark.asyncio
async def test_global_scope_serves_path_without_claude_prefix(
    claude_dir_with_agent: Path,
) -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/files/global/agents/x.md")

    assert res.status_code == 200
    body = res.json()
    assert body["repo"] == "global"
    assert body["path"] == "agents/x.md"
    assert body["content"] == "hello agent"


@pytest.mark.asyncio
async def test_global_scope_serves_path_with_claude_prefix(
    claude_dir_with_agent: Path,
) -> None:
    """AgentDetail builds `.claude/<rel>` — the global root IS claude_dir
    already, so the leading `.claude/` segment must be stripped."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/files/global/.claude/agents/x.md")

    assert res.status_code == 200
    body = res.json()
    assert body["path"] == "agents/x.md"
    assert body["content"] == "hello agent"


@pytest.mark.asyncio
async def test_global_scope_rejects_path_traversal(claude_dir_with_agent: Path) -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Percent-encode the dot segments so httpx's own URL normalization
        # doesn't collapse them away before the request ever reaches the app —
        # the raw string is what a traversal payload would actually look like.
        res = await client.get(
            "/api/files/global/..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd"
        )

    assert res.status_code == 403
