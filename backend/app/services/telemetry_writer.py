"""Atomic telemetry env-block writer for ~/.claude/settings.json.

Mirrors the safety contract of permissions_writer:
1. Atomic temp+rename write (same directory → POSIX-atomic rename).
2. Timestamped .bak before every write; old backups pruned to BACKUP_KEEP.
3. Optional if_unchanged_since mtime check → raises StaleFile on conflict.
4. Preserves ALL other keys in settings.json — only the env sub-keys we own
   are added/removed.

OTel env vars we manage (when enabled):
    CLAUDE_CODE_ENABLE_TELEMETRY = "1"
    OTEL_LOGS_EXPORTER          = "otlp"
    OTEL_EXPORTER_OTLP_PROTOCOL = "http/json"
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = <ingest_url>
    OTEL_LOGS_EXPORT_INTERVAL   = "5000"
    OTEL_METRICS_EXPORTER       = "otlp"
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT = <metrics_url>
    OTEL_METRIC_EXPORT_INTERVAL = "10000"
    OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE = "delta"

Privacy opt-ins (only written when the caller sets the flag True):
    OTEL_LOG_TOOL_DETAILS  = "1"
    OTEL_LOG_USER_PROMPTS  = "1"

When disabled, all of the above are deleted from env; every other env var
and every other top-level key is untouched.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

BACKUP_KEEP = 10

# The exact env-var keys we write/remove when toggling OTel.
_OTEL_CORE_KEYS = {
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "OTEL_LOGS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    "OTEL_LOGS_EXPORT_INTERVAL",
    # Metrics keys (Phase 3) — always written/removed alongside logs keys.
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_METRIC_EXPORT_INTERVAL",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE",
}
_OTEL_PRIVACY_KEYS = {
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_USER_PROMPTS",
}
_ALL_MANAGED_KEYS = _OTEL_CORE_KEYS | _OTEL_PRIVACY_KEYS


class StaleFile(Exception):
    """Raised when the file changed on disk since the client last read it."""


def _settings_path() -> Path:
    """Return path to the global ~/.claude/settings.json."""
    return get_settings().claude_dir / "settings.json"


def _read_json_if_present(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    return json.loads(raw)


def _prune_backups(path: Path, keep: int = BACKUP_KEEP) -> None:
    stem = path.name + ".bak."
    backups = sorted(
        (p for p in path.parent.iterdir() if p.name.startswith(stem)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            logger.debug("could not prune backup %s", old)


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def read_telemetry() -> dict:
    """Inspect ~/.claude/settings.json and return the current telemetry state.

    Returns:
        {enabled, ingestUrl, metricsUrl, exporters, options, settingsPath, fileExists, mtime}
    """
    path = _settings_path()
    exists = path.is_file()
    mtime = path.stat().st_mtime if exists else 0.0

    data: dict = {}
    if exists:
        try:
            data = _read_json_if_present(path)
        except json.JSONDecodeError as e:
            logger.warning("malformed JSON in %s: %s", path, e)

    env: dict = data.get("env") or {}
    enabled = env.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1"
    ingest_url = env.get(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        get_settings().otel_ingest_url,
    )
    metrics_url = env.get(
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        get_settings().otel_metrics_url,
    )
    exporters = {
        "logs": env.get("OTEL_LOGS_EXPORTER") if enabled else None,
        "metrics": env.get("OTEL_METRICS_EXPORTER") if enabled else None,
    }
    options = {
        "logToolDetails": env.get("OTEL_LOG_TOOL_DETAILS") == "1",
        "logUserPrompts": env.get("OTEL_LOG_USER_PROMPTS") == "1",
    }
    return {
        "enabled": enabled,
        "ingestUrl": ingest_url,
        "metricsUrl": metrics_url,
        "exporters": exporters,
        "options": options,
        "settingsPath": str(path),
        "fileExists": exists,
        "mtime": mtime,
    }


def write_telemetry(
    enabled: bool,
    log_tool_details: bool = False,
    log_user_prompts: bool = False,
    endpoint: str | None = None,
    if_unchanged_since: float | None = None,
) -> dict:
    """Write (or remove) the OTel env block in ~/.claude/settings.json.

    When enabled:
      - Sets all _OTEL_CORE_KEYS in env (using endpoint or settings.otel_ingest_url).
      - Sets OTEL_LOG_TOOL_DETAILS / OTEL_LOG_USER_PROMPTS only when the
        corresponding bool is True; deletes them otherwise.
    When disabled:
      - Deletes all _ALL_MANAGED_KEYS from env, preserving every other key.

    Returns read_telemetry() shape plus "backupPath".
    Raises StaleFile if if_unchanged_since is set and mtime has advanced.
    """
    path = _settings_path()
    existed = path.is_file()

    if existed and if_unchanged_since is not None:
        current = path.stat().st_mtime
        if current > if_unchanged_since + 0.001:
            raise StaleFile(
                f"file changed on disk (mtime {current} > expected {if_unchanged_since})"
            )

    existing: dict = {}
    if existed:
        try:
            existing = _read_json_if_present(path)
        except json.JSONDecodeError:
            raise  # don't silently clobber a broken file

    env: dict = dict(existing.get("env") or {})

    if enabled:
        settings = get_settings()
        ingest_url = endpoint or settings.otel_ingest_url
        env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        env["OTEL_LOGS_EXPORTER"] = "otlp"
        env["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/json"
        env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = ingest_url
        env["OTEL_LOGS_EXPORT_INTERVAL"] = "5000"
        # Metrics keys — always enabled together with logs (Phase 3).
        env["OTEL_METRICS_EXPORTER"] = "otlp"
        env["OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"] = settings.otel_metrics_url
        env["OTEL_METRIC_EXPORT_INTERVAL"] = "10000"
        # Pin delta temporality — our SUM aggregation math depends on it.
        env["OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"] = "delta"
        if log_tool_details:
            env["OTEL_LOG_TOOL_DETAILS"] = "1"
        else:
            env.pop("OTEL_LOG_TOOL_DETAILS", None)
        if log_user_prompts:
            env["OTEL_LOG_USER_PROMPTS"] = "1"
        else:
            env.pop("OTEL_LOG_USER_PROMPTS", None)
    else:
        for key in _ALL_MANAGED_KEYS:
            env.pop(key, None)

    # Write back — preserve every top-level key, only mutate env sub-dict.
    if env:
        existing["env"] = env
    elif "env" in existing and not env:
        # Remove the env key entirely if it's now empty.
        del existing["env"]

    # Backup BEFORE touching anything.
    backup_path = ""
    if existed:
        backup_path = str(path) + f".bak.{int(time.time())}"
        try:
            Path(backup_path).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            _prune_backups(path)
        except OSError as e:
            logger.warning("backup failed for %s: %s — proceeding anyway", path, e)
            backup_path = ""

    _atomic_write_json(path, existing)
    result = read_telemetry()
    result["backupPath"] = backup_path
    return result
