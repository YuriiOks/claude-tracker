"""HTTP-level tests for the scoped permissions read/write endpoints."""
from __future__ import annotations

import json
import time

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def claude_dir_override(tmp_path, monkeypatch):
    fake = tmp_path / ".claude"
    fake.mkdir()
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "claude_dir", fake)
    return fake


@pytest.fixture
async def client():
    from app.main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_get_scoped_missing_file(claude_dir_override, client):
    r = await client.get("/api/permissions/scoped?scope=global&target=settings_local")
    assert r.status_code == 200
    body = r.json()
    assert body["fileExists"] is False
    assert body["permissions"] == {"allow": [], "deny": [], "ask": []}


async def test_put_then_get_roundtrip(claude_dir_override, client):
    r = await client.put("/api/permissions/scoped", json={
        "scope": "global",
        "target": "settings_local",
        "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rmrf:*)"], "ask": ["Bash(git push:*)"]},
    })
    assert r.status_code == 200
    new_mtime = r.json()["mtime"]
    assert new_mtime > 0
    r2 = await client.get("/api/permissions/scoped?scope=global&target=settings_local")
    assert r2.status_code == 200
    assert r2.json()["permissions"]["allow"] == ["Bash(ls:*)"]
    assert r2.json()["mtime"] == new_mtime


async def test_invalid_target_400(claude_dir_override, client):
    r = await client.put("/api/permissions/scoped", json={
        "scope": "global",
        "target": "settings_evil",
        "permissions": {"allow": [], "deny": [], "ask": []},
    })
    assert r.status_code == 400


async def test_stale_write_409(claude_dir_override, client):
    r = await client.put("/api/permissions/scoped", json={
        "scope": "global",
        "target": "settings_local",
        "permissions": {"allow": ["a"], "deny": [], "ask": []},
    })
    mtime = r.json()["mtime"]
    path = claude_dir_override / "settings.local.json"
    new_content = json.loads(path.read_text())
    new_content["permissions"]["allow"] = ["external"]
    time.sleep(0.05)
    path.write_text(json.dumps(new_content))
    r2 = await client.put("/api/permissions/scoped", json={
        "scope": "global",
        "target": "settings_local",
        "permissions": {"allow": ["client-wins"], "deny": [], "ask": []},
        "ifUnchangedSince": mtime,
    })
    assert r2.status_code == 409
    final = json.loads(path.read_text())
    assert final["permissions"]["allow"] == ["external"]


async def test_unknown_scope_404(claude_dir_override, client):
    r = await client.put("/api/permissions/scoped", json={
        "scope": "does-not-exist",
        "target": "settings_local",
        "permissions": {"allow": [], "deny": [], "ask": []},
    })
    assert r.status_code == 404
