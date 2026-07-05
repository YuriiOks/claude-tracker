"""Unit tests for app.services.telemetry_writer.

All tests run against a tmp claude_dir (via the _isolated_db autouse fixture
in conftest.py which sets CLAUDE_DIR env var). The writer never touches the
real ~/.claude/settings.json.
"""
from __future__ import annotations

import json
import time

import pytest

from app.services import telemetry_writer as tw


@pytest.fixture
def tmp_claude_dir(tmp_path, monkeypatch):
    """Redirect settings path to a tmp directory."""
    fake = tmp_path / ".claude"
    fake.mkdir()
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "claude_dir", fake)
    return fake


# ---------------------------------------------------------------------------
# read_telemetry — no file
# ---------------------------------------------------------------------------

def test_read_telemetry_no_file(tmp_claude_dir):
    result = tw.read_telemetry()
    assert result["enabled"] is False
    assert result["fileExists"] is False
    assert result["mtime"] == 0.0
    # ingestUrl should fall back to the settings default
    assert "8765" in result["ingestUrl"] or result["ingestUrl"].startswith("http")


# ---------------------------------------------------------------------------
# write_telemetry — enable
# ---------------------------------------------------------------------------

def test_write_telemetry_enable_writes_env_keys(tmp_claude_dir):
    result = tw.write_telemetry(enabled=True)
    assert result["enabled"] is True

    path = tmp_claude_dir / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text())
    env = data["env"]

    assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert env["OTEL_LOGS_EXPORTER"] == "otlp"
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json"
    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" in env
    assert env["OTEL_LOGS_EXPORT_INTERVAL"] == "5000"

    # Privacy keys must NOT be written when bools are False (default).
    assert "OTEL_LOG_TOOL_DETAILS" not in env
    assert "OTEL_LOG_USER_PROMPTS" not in env


def test_write_telemetry_enable_with_privacy_keys(tmp_claude_dir):
    tw.write_telemetry(enabled=True, log_tool_details=True, log_user_prompts=True)
    path = tmp_claude_dir / "settings.json"
    env = json.loads(path.read_text())["env"]
    assert env["OTEL_LOG_TOOL_DETAILS"] == "1"
    assert env["OTEL_LOG_USER_PROMPTS"] == "1"


def test_write_telemetry_custom_endpoint(tmp_claude_dir):
    tw.write_telemetry(enabled=True, endpoint="http://custom:9999/v1/logs")
    path = tmp_claude_dir / "settings.json"
    env = json.loads(path.read_text())["env"]
    assert env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == "http://custom:9999/v1/logs"


# ---------------------------------------------------------------------------
# write_telemetry — disable
# ---------------------------------------------------------------------------

def test_write_telemetry_disable_removes_only_managed_keys(tmp_claude_dir):
    """Disable removes ALL OTel keys; preserves unrelated env vars + other keys."""
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({
        "agent": "tracker-orchestrator",
        "env": {
            "MY_CUSTOM_VAR": "preserved",
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:8765/v1/logs",
            "OTEL_LOGS_EXPORT_INTERVAL": "5000",
            "OTEL_LOG_TOOL_DETAILS": "1",
            "OTEL_LOG_USER_PROMPTS": "1",
        },
    }))

    result = tw.write_telemetry(enabled=False)
    assert result["enabled"] is False

    data = json.loads(path.read_text())
    assert data["agent"] == "tracker-orchestrator"  # top-level key preserved
    env = data.get("env") or {}
    assert env.get("MY_CUSTOM_VAR") == "preserved"   # unrelated env var preserved

    # All managed OTel keys removed.
    for key in tw._ALL_MANAGED_KEYS:
        assert key not in env, f"{key} should have been removed"


def test_write_telemetry_disable_empty_env_removed(tmp_claude_dir):
    """If env dict becomes empty after disabling, the key should be removed."""
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({
        "env": {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:8765/v1/logs",
            "OTEL_LOGS_EXPORT_INTERVAL": "5000",
        },
    }))

    tw.write_telemetry(enabled=False)
    data = json.loads(path.read_text())
    # env dict is empty → should not appear in the file
    assert "env" not in data


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def test_write_telemetry_creates_backup(tmp_claude_dir):
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({"env": {}}))

    result = tw.write_telemetry(enabled=True)
    assert result["backupPath"] != ""
    import pathlib
    assert pathlib.Path(result["backupPath"]).exists()


def test_write_telemetry_no_backup_for_new_file(tmp_claude_dir):
    """No backup when the file doesn't yet exist."""
    result = tw.write_telemetry(enabled=True)
    assert result["backupPath"] == ""


# ---------------------------------------------------------------------------
# StaleFile
# ---------------------------------------------------------------------------

def test_write_telemetry_stale_raises(tmp_claude_dir):
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({"env": {}}))
    original_mtime = path.stat().st_mtime

    # Simulate external edit after the client read.
    time.sleep(0.01)
    path.touch()

    with pytest.raises(tw.StaleFile):
        tw.write_telemetry(enabled=True, if_unchanged_since=original_mtime)


@pytest.mark.asyncio
async def test_write_telemetry_stale_via_router_returns_409(tmp_claude_dir):
    """PUT /api/telemetry with a stale mtime must return HTTP 409."""
    import httpx

    import app.db as _db_module
    from app.db import init_db

    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({"env": {}}))

    # Reset engine so this test gets a fresh DB at the tmp path.
    _db_module._engine = None
    _db_module._sessionmaker = None
    await init_db()

    from app.main import create_app
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.put(
            "/api/telemetry",
            json={
                "enabled": True,
                "ifUnchangedSince": 0.0,  # guaranteed stale
            },
        )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# Phase 3 — metrics env keys written/removed alongside logs keys
# ---------------------------------------------------------------------------

def test_write_telemetry_enable_writes_metrics_keys(tmp_claude_dir):
    """Enabling telemetry must write all 4 metrics env keys (Phase 3)."""
    tw.write_telemetry(enabled=True)
    path = tmp_claude_dir / "settings.json"
    env = json.loads(path.read_text())["env"]

    assert env["OTEL_METRICS_EXPORTER"] == "otlp"
    assert "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT" in env
    assert env["OTEL_METRIC_EXPORT_INTERVAL"] == "10000"
    assert env["OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"] == "delta"


def test_write_telemetry_disable_removes_metrics_keys(tmp_claude_dir):
    """Disabling telemetry must remove all 4 metrics env keys."""
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({
        "env": {
            "MY_CUSTOM_VAR": "preserved",
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:8765/v1/logs",
            "OTEL_LOGS_EXPORT_INTERVAL": "5000",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://localhost:8765/v1/metrics",
            "OTEL_METRIC_EXPORT_INTERVAL": "10000",
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
        },
    }))

    tw.write_telemetry(enabled=False)
    env = json.loads(path.read_text()).get("env") or {}

    assert "MY_CUSTOM_VAR" in env  # unrelated key preserved
    assert "OTEL_METRICS_EXPORTER" not in env
    assert "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT" not in env
    assert "OTEL_METRIC_EXPORT_INTERVAL" not in env
    assert "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE" not in env


def test_write_telemetry_preserves_unrelated_env_with_metrics(tmp_claude_dir):
    """Enabling telemetry must not clobber unrelated env vars."""
    path = tmp_claude_dir / "settings.json"
    path.write_text(json.dumps({"env": {"MY_CUSTOM_VAR": "hello"}}))

    tw.write_telemetry(enabled=True)
    env = json.loads(path.read_text())["env"]
    assert env.get("MY_CUSTOM_VAR") == "hello"


def test_read_telemetry_includes_metrics_url(tmp_claude_dir):
    """read_telemetry must return metricsUrl and exporters.metrics."""
    result = tw.read_telemetry()
    assert "metricsUrl" in result
    assert isinstance(result["metricsUrl"], str)
    assert "metrics" in result["exporters"]


def test_read_telemetry_exporters_metrics_set_when_enabled(tmp_claude_dir):
    """After enabling, exporters.metrics must be 'otlp'."""
    tw.write_telemetry(enabled=True)
    result = tw.read_telemetry()
    assert result["enabled"] is True
    assert result["exporters"]["metrics"] == "otlp"


def test_read_telemetry_exporters_metrics_none_when_disabled(tmp_claude_dir):
    """When disabled, exporters.metrics must be None."""
    result = tw.read_telemetry()  # fresh file, disabled
    assert result["exporters"]["metrics"] is None
