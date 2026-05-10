from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_repos_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "demo"
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "x.md").write_text("a")
    (repo / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}})
    )
    monkeypatch.setenv("REPO_ROOTS", str(repo))

    from app import config
    config.get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.get("/api/repos")
    assert res.status_code == 200
    body = res.json()
    assert body[0]["id"] == "demo"
    assert body[0]["isActive"] is False
    assert body[0]["permissions"]["allow"] == 1
