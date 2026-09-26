"""R-BE-31: repo=global resolves to settings.claude_dir, accepting both
`agents/x.md` and `.claude/agents/x.md` (AgentDetail sends the latter for
repo-scoped agents).

Reads under the global scope are allow-listed (agents/, skills/, commands/,
rules/, output-styles/, plus the root CLAUDE.md) — NOT deny-listed. Anything
else under ~/.claude (settings*.json, .credentials.json, statusline.sh,
projects/ transcripts, plugins/, shell-snapshots/, ...) 404s without
revealing whether it exists. Path-resolution containment (resolve +
relative_to) is kept as a second layer in case a traversal payload escapes
from inside an allow-listed directory.
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

    # Allow-listed extras used by the html-artifacts scoping tests below.
    (fake / "skills" / "html-docs" / "templates").mkdir(parents=True)
    (fake / "skills" / "html-docs" / "templates" / "spec.html").write_text("<html></html>")
    (fake / "CLAUDE.md").write_text("# global instructions")

    # Sensitive files/dirs that must stay unreachable through the files API —
    # mirrors what the reviewed BLOCKER named explicitly.
    (fake / "settings.json").write_text('{"apiKey": "sk-should-not-leak"}')
    (fake / "remote-settings.json").write_text("{}")
    (fake / "policy-limits.json").write_text("{}")
    (fake / "statusline.sh").write_text("#!/bin/sh\necho hi\n")
    (fake / "projects" / "some-repo").mkdir(parents=True)
    (fake / "projects" / "some-repo" / "session.jsonl").write_text('{"type": "user"}\n')

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
    """A traversal payload with no allow-listed prefix never reaches the
    containment check at all — the allow-list gate denies it first, as a
    404 (not a 403), so the response doesn't distinguish "outside the repo"
    from "not an allow-listed path"."""
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

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_global_scope_rejects_traversal_escaping_allowed_dir(
    claude_dir_with_agent: Path,
) -> None:
    """A payload that starts with an allow-listed prefix (`agents/`) passes
    the allow-list gate, but must still be caught by the second-layer
    resolve()+relative_to() containment check once it escapes claude_dir."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/files/global/agents%2f..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd"
        )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_global_scope_serves_root_claude_md(claude_dir_with_agent: Path) -> None:
    """The root-level CLAUDE.md is the one non-directory exemption in the
    allow-list — it's the user's global instructions file, not a secret."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/files/global/CLAUDE.md")

    assert res.status_code == 200
    assert res.json()["content"] == "# global instructions"


@pytest.mark.parametrize(
    "rel_path",
    [
        "settings.json",
        ".claude/settings.json",
        "remote-settings.json",
        "policy-limits.json",
        "statusline.sh",
        "projects/some-repo/session.jsonl",
    ],
)
@pytest.mark.asyncio
async def test_global_scope_blocks_non_allowlisted_paths(
    claude_dir_with_agent: Path, rel_path: str
) -> None:
    """R-BE-31 follow-up (reviewer BLOCKER): repo=global must not serve
    settings.json, remote-settings.json, policy-limits.json, statusline.sh,
    or anything under projects/ — only agents/skills/commands/rules/
    output-styles + the root CLAUDE.md are reachable."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/files/global/{rel_path}")

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_global_html_artifacts_allowlisted_dir_lists_files(
    claude_dir_with_agent: Path,
) -> None:
    """The same allow-list applies to the artifacts-listing endpoint —
    skills/<name>/templates is allow-listed (SkillTemplatesPanel's dir)."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/repos/global/artifacts/html",
            params={"dir": ".claude/skills/html-docs/templates"},
        )

    assert res.status_code == 200
    names = [f["name"] for f in res.json()]
    assert names == ["spec"]


@pytest.mark.asyncio
async def test_global_html_artifacts_non_allowlisted_dir_returns_empty(
    claude_dir_with_agent: Path,
) -> None:
    """`dir=docs` (the endpoint's own default) is not allow-listed for the
    global scope -- returns an empty list rather than 404, matching the
    existing "missing directory" response shape so no distinction leaks."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/repos/global/artifacts/html")

    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rel_path",
    [
        # %2f keeps httpx from normalizing the dot-segment client-side.
        "agents/..%2fsettings.json",
        ".claude/agents/..%2fsettings.json",
        "skills/..%2fprojects/some-repo/session.jsonl",
    ],
)
async def test_global_scope_blocks_dotdot_out_of_allowed_dir(
    claude_dir_with_agent: Path, rel_path: str
) -> None:
    """An allow-listed prefix followed by `..` must not reach a denied file
    that still sits inside claude_dir (containment alone would accept it)."""
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/files/global/{rel_path}")

    assert res.status_code == 404
    assert "sk-should-not-leak" not in res.text


@pytest.mark.asyncio
async def test_global_scope_blocks_symlink_out_of_allowed_dir(
    claude_dir_with_agent: Path,
) -> None:
    """A symlink inside an allow-listed dir pointing at a denied file is
    judged by its resolved target, not its link path."""
    (claude_dir_with_agent / "agents" / "leak.json").symlink_to(
        claude_dir_with_agent / "settings.json"
    )
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/files/global/agents/leak.json")

    assert res.status_code == 404
    assert "sk-should-not-leak" not in res.text


@pytest.mark.asyncio
async def test_global_html_artifacts_blocks_dotdot_dir(claude_dir_with_agent: Path) -> None:
    (claude_dir_with_agent / "projects" / "some-repo" / "leak.html").write_text("<html></html>")
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/repos/global/artifacts/html", params={"dir": "skills/../projects/some-repo"}
        )

    assert res.status_code == 200
    assert res.json() == []
