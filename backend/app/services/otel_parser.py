"""Pure OTLP/HTTP-json log parser — no DB, no I/O.

Decodes a Claude Code OTLP logs export payload into a flat list of
ParsedOtelEvent dataclasses. Unknown or malformed records are skipped
with a warning — one bad record must not abort the whole batch.

Wire encoding (verified against claude 2.1.158 capture):
  {resourceLogs:[{resource:{attributes:[KV]},scopeLogs:[{scope:...,logRecords:[REC]}]}]}
  REC: {timeUnixNano:"<ns>", body:{stringValue:"claude_code.<name>"}, attributes:[KV]}
  KV:  {key:"...", value:<AnyValue>}
  AnyValue oneof: stringValue, intValue (JSON number OR string), doubleValue, boolValue,
                  arrayValue.values[], kvlistValue.values[], bytesValue (base64 str)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Prefix stripped from body.stringValue to yield a short event name.
_CC_PREFIX = "claude_code."


@dataclass
class ParsedOtelEvent:
    event_name: str
    ts: datetime          # UTC naive (timezone stripped after conversion)
    session_id: str | None
    prompt_id: str | None
    event_sequence: int | None
    # Merged resource attrs + record attrs into one flat dict.
    attrs: dict = field(default_factory=dict)


def _anyvalue(v: dict) -> object:  # noqa: ANN001
    """Decode a single AnyValue oneof into a Python scalar or container.

    Handles both JSON-number and JSON-string forms of intValue (the Claude
    Code exporter sends numeric JSON numbers, but the spec allows strings).
    Returns None for unknown or empty shapes so callers can decide how to
    handle the gap.
    """
    if not isinstance(v, dict):
        return None
    if "stringValue" in v:
        return str(v["stringValue"])
    if "intValue" in v:
        raw = v["intValue"]
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if "doubleValue" in v:
        raw = v["doubleValue"]
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        items = v["arrayValue"].get("values") or []
        return [_anyvalue(item) for item in items if isinstance(item, dict)]
    if "kvlistValue" in v:
        pairs = v["kvlistValue"].get("values") or []
        out: dict[str, object] = {}
        for kv in pairs:
            if isinstance(kv, dict) and "key" in kv and "value" in kv:
                out[kv["key"]] = _anyvalue(kv["value"])
        return out
    if "bytesValue" in v:
        # Return as base64 string — callers that need bytes can decode.
        return str(v["bytesValue"])
    return None


def _decode_kv_list(kv_list: list[dict]) -> dict:
    """Decode a list of {key, value} KV pairs into a flat dict."""
    out: dict[str, object] = {}
    for kv in kv_list:
        if not isinstance(kv, dict):
            continue
        key = kv.get("key")
        val = kv.get("value")
        if key and isinstance(val, dict):
            decoded = _anyvalue(val)
            if decoded is not None:
                out[str(key)] = decoded
    return out


def _parse_time_unix_nano(raw: object) -> datetime | None:
    """Convert a timeUnixNano value (string or int of nanoseconds) → UTC datetime."""
    try:
        ns = int(raw)
        return datetime.fromtimestamp(ns / 1e9, tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def parse_logs_export(payload: dict) -> list[ParsedOtelEvent]:  # noqa: ANN001
    """Walk resourceLogs → scopeLogs → logRecords and return ParsedOtelEvents.

    Skips (with a warning) any record that is malformed or missing required
    fields. Never raises — one bad batch line should not abort ingestion.
    """
    results: list[ParsedOtelEvent] = []

    resource_logs = payload.get("resourceLogs") or []
    if not isinstance(resource_logs, list):
        logger.warning("otel_parser: resourceLogs is not a list — skipping payload")
        return results

    for rl_idx, resource_log in enumerate(resource_logs):
        if not isinstance(resource_log, dict):
            continue

        # Decode resource-level attributes (host.arch, service.name, …).
        resource_attrs: dict = {}
        resource = resource_log.get("resource") or {}
        if isinstance(resource, dict):
            raw_res_attrs = resource.get("attributes") or []
            if isinstance(raw_res_attrs, list):
                resource_attrs = _decode_kv_list(raw_res_attrs)

        scope_logs = resource_log.get("scopeLogs") or []
        if not isinstance(scope_logs, list):
            continue

        for sl_idx, scope_log in enumerate(scope_logs):
            if not isinstance(scope_log, dict):
                continue

            log_records = scope_log.get("logRecords") or []
            if not isinstance(log_records, list):
                continue

            for rec_idx, rec in enumerate(log_records):
                try:
                    result = _parse_record(rec, resource_attrs)
                    if result is not None:
                        results.append(result)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "otel_parser: skipping record rl[%d].sl[%d].rec[%d]: %s",
                        rl_idx, sl_idx, rec_idx, exc,
                    )

    return results


def _parse_record(rec: dict, resource_attrs: dict) -> ParsedOtelEvent | None:
    """Parse one logRecord dict.

    Returns None (without raising) if the record is missing required fields.
    """
    if not isinstance(rec, dict):
        return None

    # -- Timestamp ----------------------------------------------------------
    ts_raw = rec.get("timeUnixNano")
    if ts_raw is None:
        logger.debug("otel_parser: record missing timeUnixNano — skipping")
        return None
    ts = _parse_time_unix_nano(ts_raw)
    if ts is None:
        logger.warning("otel_parser: unparseable timeUnixNano=%r — skipping", ts_raw)
        return None

    # -- Record-level attributes --------------------------------------------
    raw_attrs = rec.get("attributes") or []
    rec_attrs: dict = {}
    if isinstance(raw_attrs, list):
        rec_attrs = _decode_kv_list(raw_attrs)

    # -- Event name ---------------------------------------------------------
    # Prefer event.name attr; fall back to stripping "claude_code." from body.
    event_name: str = ""
    if "event.name" in rec_attrs:
        event_name = str(rec_attrs["event.name"])
    else:
        body = rec.get("body") or {}
        body_str = body.get("stringValue", "") if isinstance(body, dict) else ""
        if body_str.startswith(_CC_PREFIX):
            event_name = body_str[len(_CC_PREFIX):]
        else:
            event_name = body_str

    if not event_name:
        logger.debug("otel_parser: record has no event name — skipping")
        return None

    # -- Standard fields ----------------------------------------------------
    session_id: str | None = rec_attrs.get("session.id")  # type: ignore[assignment]
    prompt_id: str | None = rec_attrs.get("prompt.id")    # type: ignore[assignment]
    seq_raw = rec_attrs.get("event.sequence")
    event_sequence: int | None = int(seq_raw) if seq_raw is not None else None

    # -- Merged attrs (resource first, record overrides) --------------------
    merged = {**resource_attrs, **rec_attrs}

    return ParsedOtelEvent(
        event_name=event_name,
        ts=ts,
        session_id=session_id,
        prompt_id=prompt_id,
        event_sequence=event_sequence,
        attrs=merged,
    )
