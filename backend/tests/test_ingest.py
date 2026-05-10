from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest


def _write_session(jsonl: Path, session_id: str, repo_path: Path, ts: str = "2026-05-10T10:00:00Z") -> None:
    jsonl.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": session_id,
                "cwd": str(repo_path),
                "timestamp": ts,
                "message": {"content": "do a thing"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "sessionId": session_id,
                "cwd": str(repo_path),
                "timestamp": "2026-05-10T10:00:30Z",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            }
        )
        + "\n"
    )


@pytest.mark.asyncio
async def test_ingest_and_sessions_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    claude = tmp_path / "claude"
    proj = claude / "projects" / "myrepo-encoded"
    proj.mkdir(parents=True)
    _write_session(proj / "abc.jsonl", "abc-session", repo)

    monkeypatch.setenv("CLAUDE_DIR", str(claude))
    monkeypatch.setenv("REPO_ROOTS", str(repo))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))

    from app import config

    config.get_settings.cache_clear()
    # Reset module-level engine so the new DB_PATH is honored.
    import app.db as db_mod

    db_mod._engine = None
    db_mod._sessionmaker = None

    from app.services.ingest import ingest_all
    result = await ingest_all()
    assert result["new"] == 1
    assert result["events"] >= 1

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        sessions_res = await c.get("/api/sessions")
        live_res = await c.get("/api/live/recent")
    assert sessions_res.status_code == 200
    body = sessions_res.json()
    assert len(body) == 1
    assert body[0]["repo"] == "myrepo"
    assert body[0]["tokens"] == 150
    assert body[0]["cost"] >= 0
    assert live_res.status_code == 200
    assert isinstance(live_res.json(), list)
