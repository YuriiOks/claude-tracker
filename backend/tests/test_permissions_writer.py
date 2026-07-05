"""Unit tests for the permissions writer service."""
from __future__ import annotations

import json
import time

import pytest

from app.services import permissions_writer as pw


@pytest.fixture
def tmp_claude_dir(tmp_path, monkeypatch):
    """A fake ~/.claude/ for the writer to target."""
    fake = tmp_path / ".claude"
    fake.mkdir()
    # Patch the settings.claude_dir resolver
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "claude_dir", fake)
    return fake


def test_resolve_paths(tmp_claude_dir):
    p1 = pw.resolve_settings_path("global", "settings")
    assert p1.name == "settings.json"
    assert p1.parent == tmp_claude_dir
    p2 = pw.resolve_settings_path("global", "settings_local")
    assert p2.name == "settings.local.json"


def test_invalid_target_rejected(tmp_claude_dir):
    with pytest.raises(ValueError):
        pw.resolve_settings_path("global", "settings_secret")


def test_read_when_file_missing(tmp_claude_dir):
    out = pw.read_permissions("global", "settings_local")
    assert out["file_exists"] is False
    assert out["mtime"] == 0.0
    assert out["permissions"] == {"allow": [], "deny": [], "ask": []}


def test_write_creates_file_and_preserves_other_keys(tmp_claude_dir):
    # Seed with an existing file that has unrelated keys.
    path = tmp_claude_dir / "settings.local.json"
    path.write_text(json.dumps({
        "agent": "tracker-orchestrator",
        "env": {"K": "V"},
        "permissions": {"allow": ["old"], "deny": [], "ask": []},
    }))

    result = pw.write_permissions(
        scope="global", target="settings_local",
        permissions={"allow": ["new"], "deny": ["bad"], "ask": ["maybe"]},
    )
    assert result["file_path"].endswith("settings.local.json")
    assert result["mtime"] > 0
    assert "bak" in result["backup_path"]

    saved = json.loads(path.read_text())
    assert saved["agent"] == "tracker-orchestrator"  # preserved
    assert saved["env"] == {"K": "V"}                # preserved
    assert saved["permissions"]["allow"] == ["new"]  # replaced
    assert saved["permissions"]["deny"] == ["bad"]
    assert saved["permissions"]["ask"] == ["maybe"]


def test_dedupe_preserves_first_seen_order(tmp_claude_dir):
    pw.write_permissions(
        scope="global", target="settings_local",
        permissions={
            "allow": ["A", "B", "A", "C", "B"],
            "deny": ["", "  ", "X"],
            "ask": [],
        },
    )
    saved = json.loads((tmp_claude_dir / "settings.local.json").read_text())
    assert saved["permissions"]["allow"] == ["A", "B", "C"]
    assert saved["permissions"]["deny"] == ["X"]  # empty/whitespace dropped


def test_stale_file_detection(tmp_claude_dir):
    path = tmp_claude_dir / "settings.local.json"
    path.write_text(json.dumps({"permissions": {"allow": [], "deny": [], "ask": []}}))
    original_mtime = path.stat().st_mtime
    # Simulate the file being touched by something else after the client read it
    time.sleep(0.01)
    path.touch()
    with pytest.raises(pw.StaleFile):
        pw.write_permissions(
            scope="global", target="settings_local",
            permissions={"allow": ["X"], "deny": [], "ask": []},
            if_unchanged_since=original_mtime,
        )


def test_backup_files_pruned_to_window(tmp_claude_dir):
    path = tmp_claude_dir / "settings.local.json"
    path.write_text(json.dumps({"permissions": {"allow": [], "deny": [], "ask": []}}))
    for i in range(pw.BACKUP_KEEP + 5):
        pw.write_permissions(
            scope="global", target="settings_local",
            permissions={"allow": [f"r{i}"], "deny": [], "ask": []},
        )
        time.sleep(0.01)  # ensure mtime ticks
    backups = list(tmp_claude_dir.glob("settings.local.json.bak.*"))
    assert len(backups) <= pw.BACKUP_KEEP


def test_atomic_write_uses_rename(tmp_claude_dir, monkeypatch):
    # If json.dumps raises, the original file should remain.
    path = tmp_claude_dir / "settings.local.json"
    path.write_text('{"permissions": {"allow": ["original"], "deny": [], "ask": []}}')
    original = path.read_text()

    def boom(*a, **kw):
        raise RuntimeError("simulated write failure")
    monkeypatch.setattr(pw, "_atomic_write_json", boom)
    with pytest.raises(RuntimeError):
        pw.write_permissions(
            scope="global", target="settings_local",
            permissions={"allow": ["NEW"], "deny": [], "ask": []},
        )
    assert path.read_text() == original
