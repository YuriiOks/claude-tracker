from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "skills" / "my-skill").mkdir(parents=True)
    (repo / ".claude" / "commands").mkdir()
    (repo / ".claude" / "rules").mkdir()
    (repo / ".claude" / "hooks").mkdir()

    (repo / ".claude" / "agents" / "tester.md").write_text("---\nrole: tester\n---\nbody")
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").write_text("# Skill\n")
    (repo / ".claude" / "commands" / "run-tests.md").write_text("# /run-tests\n")
    (repo / ".claude" / "rules" / "conventions.md").write_text("rule\n")
    (repo / ".claude" / "hooks" / "pre.sh").write_text("#!/bin/sh\n")
    (repo / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(ls:*)", "Bash(pytest:*)"],
                    "deny": ["Bash(rm -rf:*)"],
                    "ask": [],
                },
                "plugins": {"linear": {}},
                "mcpServers": {"filesystem": {"command": "x"}},
            }
        )
    )
    return repo


def test_scan_all_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path, "demo")
    monkeypatch.setenv("REPO_ROOTS", str(repo))

    from app import config
    config.get_settings.cache_clear()
    from app.services.repo_scanner import scan_all_repos

    repos = scan_all_repos()
    assert len(repos) == 1
    r = repos[0]
    assert r.id == "demo"
    assert r.agents == ["tester"]
    assert r.skills == ["my-skill"]
    assert r.commands == ["/run-tests"]
    assert r.rules == ["conventions"]
    assert r.plugins == ["linear"]
    assert r.mcp == ["filesystem"]
    assert r.permissions.allow == 2
    assert r.permissions.deny == 1
    assert r.permissions.ask == 0


def test_scan_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / "claude"
    (claude_dir / "agents").mkdir(parents=True)
    (claude_dir / "skills" / "html-docs").mkdir(parents=True)
    (claude_dir / "commands").mkdir()
    (claude_dir / "agents" / "doc-author.md").write_text("---\nrole: docs\n---\n")
    (claude_dir / "skills" / "html-docs" / "SKILL.md").write_text("# skill")
    (claude_dir / "commands" / "doc.md").write_text("# /doc")
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read(**/*)"], "deny": [], "ask": []},
                "plugins": {},
                "mcpServers": {},
            }
        )
    )
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))

    from app import config
    config.get_settings.cache_clear()
    from app.services.repo_scanner import scan_global

    g = scan_global()
    assert g.id == "global"
    assert g.agents == ["doc-author"]
    assert g.skills == ["html-docs"]
    assert g.commands == ["/doc"]
    assert g.permissions.allow == 1
    assert g.file_sizes.skills["html-docs"] > 0
