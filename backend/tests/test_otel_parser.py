"""Unit tests for app.services.otel_parser.

Tests parse against the real anonymized fixture (09_v1_logs.json equivalent,
saved as fixtures/otel/logs_sample.json) plus inline synthetic records
that cover edge cases not present in any real capture.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.otel_parser import (
    _anyvalue,
    _parse_time_unix_nano,
    parse_logs_export,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "otel" / "logs_sample.json"


@pytest.fixture
def fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


# ---------------------------------------------------------------------------
# _parse_time_unix_nano
# ---------------------------------------------------------------------------

def test_parse_time_unix_nano_string():
    ts = _parse_time_unix_nano("1780251963638000000")
    assert isinstance(ts, datetime)
    assert ts.year == 2026
    assert ts.month == 5
    assert ts.day == 31
    assert ts.tzinfo is None  # stored as UTC-naive


def test_parse_time_unix_nano_int():
    ts = _parse_time_unix_nano(1780251963638000000)
    assert isinstance(ts, datetime)
    assert ts.year == 2026


def test_parse_time_unix_nano_garbage():
    assert _parse_time_unix_nano("not-a-number") is None
    assert _parse_time_unix_nano(None) is None


# ---------------------------------------------------------------------------
# _anyvalue decoder
# ---------------------------------------------------------------------------

def test_anyvalue_string():
    assert _anyvalue({"stringValue": "hello"}) == "hello"


def test_anyvalue_int_as_number():
    """intValue as JSON number (real wire format from claude 2.1.158)."""
    assert _anyvalue({"intValue": 42}) == 42
    assert isinstance(_anyvalue({"intValue": 94}), int)


def test_anyvalue_int_as_string():
    """intValue as JSON string (spec allows this; synthetic test case)."""
    assert _anyvalue({"intValue": "99"}) == 99


def test_anyvalue_double():
    """doubleValue — present in api_request events (cost_usd)."""
    result = _anyvalue({"doubleValue": 0.0995565})
    assert isinstance(result, float)
    assert abs(result - 0.0995565) < 1e-9


def test_anyvalue_bool():
    """boolValue — present in mcp_server_connection events (is_plugin)."""
    assert _anyvalue({"boolValue": True}) is True
    assert _anyvalue({"boolValue": False}) is False


def test_anyvalue_array():
    result = _anyvalue({"arrayValue": {"values": [{"intValue": 1}, {"intValue": 2}]}})
    assert result == [1, 2]


def test_anyvalue_kvlist():
    result = _anyvalue({"kvlistValue": {"values": [
        {"key": "a", "value": {"stringValue": "x"}},
        {"key": "b", "value": {"intValue": 7}},
    ]}})
    assert result == {"a": "x", "b": 7}


def test_anyvalue_bytes():
    result = _anyvalue({"bytesValue": "aGVsbG8="})  # base64 "hello"
    assert isinstance(result, str)


def test_anyvalue_unknown_shape():
    """Unknown AnyValue shape → None (not an error)."""
    assert _anyvalue({"unknownField": "x"}) is None
    assert _anyvalue({}) is None
    assert _anyvalue("not-a-dict") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_logs_export — real fixture
# ---------------------------------------------------------------------------

def test_parse_fixture_returns_four_events(fixture_payload):
    events = parse_logs_export(fixture_payload)
    assert len(events) == 4


def test_parse_fixture_event_names(fixture_payload):
    events = parse_logs_export(fixture_payload)
    names = [e.event_name for e in events]
    assert "mcp_server_connection" in names
    assert "api_request" in names
    assert "hook_execution_start" in names


def test_parse_fixture_session_id(fixture_payload):
    events = parse_logs_export(fixture_payload)
    for e in events:
        assert e.session_id == "956ec528-c412-418d-b1df-ec9595f734ad"


def test_parse_fixture_sequence_numbers(fixture_payload):
    events = parse_logs_export(fixture_payload)
    seqs = sorted(e.event_sequence for e in events if e.event_sequence is not None)
    assert seqs == [93, 94, 95, 96]


def test_parse_fixture_api_request_double_value(fixture_payload):
    """api_request event carries doubleValue cost_usd — must decode to float."""
    events = parse_logs_export(fixture_payload)
    api_req = next(e for e in events if e.event_name == "api_request")
    cost = api_req.attrs.get("cost_usd")
    assert isinstance(cost, float)
    assert abs(cost - 0.0995565) < 1e-6


def test_parse_fixture_bool_value(fixture_payload):
    """mcp_server_connection events carry boolValue is_plugin — must be Python bool."""
    events = parse_logs_export(fixture_payload)
    mcp = next(e for e in events if e.event_name == "mcp_server_connection")
    is_plugin = mcp.attrs.get("is_plugin")
    assert isinstance(is_plugin, bool)


def test_parse_fixture_int_values(fixture_payload):
    """api_request intValue fields (input_tokens, duration_ms) decode to int."""
    events = parse_logs_export(fixture_payload)
    api_req = next(e for e in events if e.event_name == "api_request")
    assert isinstance(api_req.attrs.get("input_tokens"), int)
    assert isinstance(api_req.attrs.get("duration_ms"), int)


def test_parse_fixture_prompt_id(fixture_payload):
    events = parse_logs_export(fixture_payload)
    for e in events:
        assert e.prompt_id == "936f702b-9449-4485-9ea9-f5620f942544"


def test_parse_fixture_ts_is_utc_naive(fixture_payload):
    events = parse_logs_export(fixture_payload)
    for e in events:
        assert isinstance(e.ts, datetime)
        assert e.ts.tzinfo is None


def test_parse_fixture_resource_attrs_merged(fixture_payload):
    """Resource-level attrs (service.name, host.arch) should be in merged attrs."""
    events = parse_logs_export(fixture_payload)
    for e in events:
        assert e.attrs.get("service.name") == "claude-code"
        assert e.attrs.get("host.arch") == "arm64"


# ---------------------------------------------------------------------------
# parse_logs_export — resilience / edge cases
# ---------------------------------------------------------------------------

def test_parse_empty_payload():
    assert parse_logs_export({}) == []


def test_parse_garbage_body():
    assert parse_logs_export({"resourceLogs": "not-a-list"}) == []


def test_parse_record_missing_time_is_skipped():
    """A logRecord without timeUnixNano is skipped, rest of batch still parsed."""
    payload = {
        "resourceLogs": [{
            "resource": {"attributes": []},
            "scopeLogs": [{
                "scope": {},
                "logRecords": [
                    # Bad record — no timeUnixNano
                    {
                        "body": {"stringValue": "claude_code.api_request"},
                        "attributes": [
                            {"key": "event.name", "value": {"stringValue": "api_request"}},
                            {"key": "event.sequence", "value": {"intValue": 1}},
                        ],
                    },
                    # Good record
                    {
                        "timeUnixNano": "1780251963638000000",
                        "body": {"stringValue": "claude_code.hook_execution_start"},
                        "attributes": [
                            {"key": "event.name", "value": {"stringValue": "hook_execution_start"}},
                            {"key": "session.id", "value": {"stringValue": "sess-abc"}},
                            {"key": "event.sequence", "value": {"intValue": 2}},
                        ],
                    },
                ],
            }],
        }],
    }
    events = parse_logs_export(payload)
    assert len(events) == 1
    assert events[0].event_name == "hook_execution_start"


def test_parse_body_fallback_when_no_event_name_attr():
    """Falls back to stripping 'claude_code.' from body.stringValue."""
    payload = {
        "resourceLogs": [{
            "resource": {"attributes": []},
            "scopeLogs": [{
                "scope": {},
                "logRecords": [{
                    "timeUnixNano": "1780251963638000000",
                    "body": {"stringValue": "claude_code.user_prompt"},
                    "attributes": [],
                }],
            }],
        }],
    }
    events = parse_logs_export(payload)
    assert len(events) == 1
    assert events[0].event_name == "user_prompt"


def test_parse_int_as_string_in_sequence():
    """Synthetic: event.sequence delivered as intValue-string must still parse."""
    payload = {
        "resourceLogs": [{
            "resource": {"attributes": []},
            "scopeLogs": [{
                "scope": {},
                "logRecords": [{
                    "timeUnixNano": "1780251963638000000",
                    "body": {"stringValue": "claude_code.api_request"},
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        # intValue delivered as a JSON string (spec allows it)
                        {"key": "event.sequence", "value": {"intValue": "77"}},
                        {"key": "session.id", "value": {"stringValue": "sess-synth"}},
                    ],
                }],
            }],
        }],
    }
    events = parse_logs_export(payload)
    assert len(events) == 1
    assert events[0].event_sequence == 77
    assert isinstance(events[0].event_sequence, int)
