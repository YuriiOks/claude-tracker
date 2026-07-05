"""Unit tests for app.services.otel_metrics_parser.

All tests use the real fixture files (PII-scrubbed) or inline payloads.
No DB — the parser is pure.

Fixture facts (from metrics_sample.json — batch 05):
  - claude_code.cost.usage: 1 DP, asDouble=0.10187775 (float)
  - claude_code.token.usage: 4 DPs
      input: asDouble=3   (JSON int, parsed as float -> 3.0)
      output: asDouble=13 (JSON int -> 13.0)
      cacheRead: asDouble=0  <- the falsy-zero trap case; must NOT be skipped
      cacheCreation: asDouble=27113 (JSON int -> 27113.0)

Fixture facts (metrics_sample_b.json -- batch 02):
  - claude_code.session.count: 1 DP, asDouble=1

Fixture facts (metrics_sample_c.json -- batch 07):
  - claude_code.active_time.total: 1 DP, asDouble=5.76

Total across all 3 batches: 7 datapoints.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.otel_metrics_parser import ParsedOtelMetric, _attrs_key, parse_metrics_export

FIXTURES = Path(__file__).parent / "fixtures" / "otel"
BATCH_A = FIXTURES / "metrics_sample.json"    # cost + 4 token types
BATCH_B = FIXTURES / "metrics_sample_b.json"  # session.count
BATCH_C = FIXTURES / "metrics_sample_c.json"  # active_time


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _parse(path: Path) -> list[ParsedOtelMetric]:
    return parse_metrics_export(_load(path))


# ---------------------------------------------------------------------------
# Basic parsing from real fixtures
# ---------------------------------------------------------------------------

def test_batch_a_yields_five_rows():
    """Batch A has cost (1 DP) + token (4 DPs) = 5 rows."""
    rows = _parse(BATCH_A)
    assert len(rows) == 5


def test_batch_b_yields_one_row():
    rows = _parse(BATCH_B)
    assert len(rows) == 1
    assert rows[0].metric_name == "claude_code.session.count"


def test_batch_c_yields_one_row():
    rows = _parse(BATCH_C)
    assert len(rows) == 1
    assert rows[0].metric_name == "claude_code.active_time.total"


def test_total_across_all_batches_is_seven():
    all_rows = _parse(BATCH_A) + _parse(BATCH_B) + _parse(BATCH_C)
    assert len(all_rows) == 7


# ---------------------------------------------------------------------------
# Value parsing correctness
# ---------------------------------------------------------------------------

def test_cost_asDouble_float_parsed():
    """Cost value is a JSON float -- must parse correctly."""
    rows = _parse(BATCH_A)
    cost_rows = [r for r in rows if r.metric_name == "claude_code.cost.usage"]
    assert len(cost_rows) == 1
    assert abs(cost_rows[0].value - 0.10187775) < 1e-9
    assert isinstance(cost_rows[0].value, float)


def test_token_input_asDouble_int_json_parsed():
    """token.usage input=3 -- asDouble is a JSON integer, parsed to float 3.0.

    Note: r.attrs is a dict (not JSON string) in parser output.
    """
    rows = _parse(BATCH_A)
    token_rows = [r for r in rows if r.metric_name == "claude_code.token.usage"]
    # attrs is already a dict in ParsedOtelMetric (JSON-stringified only on DB insert)
    types = {r.attrs["type"]: r.value for r in token_rows}
    assert types["input"] == 3.0
    assert isinstance(types["input"], float)


def test_cacheRead_asDouble_zero_not_skipped():
    """asDouble=0 must NOT be skipped -- falsy-value check would silently drop the row."""
    rows = _parse(BATCH_A)
    token_rows = [r for r in rows if r.metric_name == "claude_code.token.usage"]
    # attrs is already a dict in ParsedOtelMetric
    types = {r.attrs["type"]: r.value for r in token_rows}
    assert "cacheRead" in types, "cacheRead=0 was incorrectly skipped"
    assert types["cacheRead"] == 0.0


def test_cacheCreation_value():
    rows = _parse(BATCH_A)
    token_rows = [r for r in rows if r.metric_name == "claude_code.token.usage"]
    types = {r.attrs["type"]: r.value for r in token_rows}
    assert types["cacheCreation"] == 27113.0


def test_active_time_value():
    rows = _parse(BATCH_C)
    assert abs(rows[0].value - 5.76) < 1e-9


# ---------------------------------------------------------------------------
# Metadata: temporality, kind, is_monotonic
# ---------------------------------------------------------------------------

def test_cost_row_is_delta_sum_monotonic():
    rows = _parse(BATCH_A)
    cost = next(r for r in rows if r.metric_name == "claude_code.cost.usage")
    assert cost.kind == "sum"
    assert cost.temporality == 1  # DELTA
    assert cost.is_monotonic is True


def test_active_time_row_metadata():
    rows = _parse(BATCH_C)
    row = rows[0]
    assert row.kind == "sum"
    assert row.temporality == 1
    assert row.is_monotonic is True
    assert row.unit == "s"


def test_session_count_unit_empty():
    rows = _parse(BATCH_B)
    assert rows[0].unit == ""


# ---------------------------------------------------------------------------
# attrs_key stability
# ---------------------------------------------------------------------------

def test_attrs_key_is_stable():
    """Same attrs dict -> same attrs_key regardless of key insertion order."""
    attrs1 = {"model": "claude-sonnet-4-6", "type": "input", "session.id": "abc"}
    attrs2 = {"session.id": "abc", "type": "input", "model": "claude-sonnet-4-6"}
    assert _attrs_key(attrs1) == _attrs_key(attrs2)


def test_attrs_key_is_sha1_hex():
    attrs = {"model": "test", "type": "input"}
    key = _attrs_key(attrs)
    # SHA-1 produces a 40-char hex string.
    assert len(key) == 40
    assert all(c in "0123456789abcdef" for c in key)


def test_real_rows_have_attrs_key_populated():
    rows = _parse(BATCH_A)
    for row in rows:
        assert row.attrs_key, "attrs_key must not be empty"
        assert len(row.attrs_key) == 40


# ---------------------------------------------------------------------------
# start_ts and ts parsing
# ---------------------------------------------------------------------------

def test_cost_row_timestamps_present():
    rows = _parse(BATCH_A)
    cost = next(r for r in rows if r.metric_name == "claude_code.cost.usage")
    assert cost.ts is not None
    assert cost.start_ts is not None
    # start_ts must be before or equal to ts.
    assert cost.start_ts <= cost.ts


# ---------------------------------------------------------------------------
# Resilience -- garbage / unknown shapes
# ---------------------------------------------------------------------------

def test_empty_resource_metrics_returns_empty():
    assert parse_metrics_export({"resourceMetrics": []}) == []


def test_missing_resource_metrics_key_returns_empty():
    assert parse_metrics_export({}) == []


def test_garbage_payload_returns_empty():
    assert parse_metrics_export({"resourceMetrics": "not-a-list"}) == []


def test_histogram_metric_is_skipped():
    """Histogram metrics must be silently skipped -- we only handle sum/gauge."""
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "metrics": [{
                    "name": "claude_code.some_histogram",
                    "unit": "ms",
                    "histogram": {
                        "aggregationTemporality": 1,
                        "dataPoints": [{"timeUnixNano": "1780256082340000000", "asDouble": 1.0}],
                    },
                }],
            }],
        }],
    }
    assert parse_metrics_export(payload) == []


def test_missing_asDouble_and_asInt_skipped():
    """DataPoint with no value field must be skipped, not raise."""
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "metrics": [{
                    "name": "claude_code.cost.usage",
                    "unit": "USD",
                    "sum": {
                        "aggregationTemporality": 1,
                        "isMonotonic": True,
                        "dataPoints": [{"timeUnixNano": "1780256082340000000", "attributes": []}],
                    },
                }],
            }],
        }],
    }
    assert parse_metrics_export(payload) == []


def test_asInt_string_decoded():
    """asInt is spec'd as a JSON string -- must convert to float correctly."""
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "metrics": [{
                    "name": "claude_code.session.count",
                    "unit": "",
                    "sum": {
                        "aggregationTemporality": 1,
                        "isMonotonic": True,
                        "dataPoints": [{
                            "timeUnixNano": "1780256082340000000",
                            "attributes": [],
                            "asInt": "42",
                        }],
                    },
                }],
            }],
        }],
    }
    rows = parse_metrics_export(payload)
    assert len(rows) == 1
    assert rows[0].value == 42.0


def test_gauge_metric_parsed():
    """Gauge metrics must be decoded (defensive path)."""
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "metrics": [{
                    "name": "claude_code.some_gauge",
                    "unit": "count",
                    "gauge": {
                        "dataPoints": [{
                            "timeUnixNano": "1780256082340000000",
                            "attributes": [],
                            "asDouble": 3.14,
                        }],
                    },
                }],
            }],
        }],
    }
    rows = parse_metrics_export(payload)
    assert len(rows) == 1
    assert rows[0].kind == "gauge"
    assert rows[0].temporality == 0
    assert rows[0].is_monotonic is False
    assert abs(rows[0].value - 3.14) < 1e-9


def test_synthetic_code_edit_tool_decision():
    """Supplementary synthetic metric for coverage of non-cost/token names.

    SYNTHETIC -- not from a real claude 2.1.158 capture. Follows the same
    OTLP wire encoding verified against real fixtures. Clearly marked.
    """
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "claude-code"}},
            ]},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "metrics": [
                    {
                        "name": "claude_code.code_edit_tool.decision",
                        "unit": "count",
                        "sum": {
                            "aggregationTemporality": 1,
                            "isMonotonic": True,
                            "dataPoints": [{
                                "attributes": [
                                    {"key": "decision", "value": {"stringValue": "accept"}},
                                ],
                                "startTimeUnixNano": "1780256081804000000",
                                "timeUnixNano": "1780256082340000000",
                                "asDouble": 5,
                            }],
                        },
                    },
                    {
                        "name": "claude_code.lines_of_code.count",
                        "unit": "lines",
                        "sum": {
                            "aggregationTemporality": 1,
                            "isMonotonic": True,
                            "dataPoints": [{
                                "attributes": [
                                    {"key": "language", "value": {"stringValue": "python"}},
                                ],
                                "startTimeUnixNano": "1780256081804000000",
                                "timeUnixNano": "1780256082340000000",
                                "asInt": "120",
                            }],
                        },
                    },
                ],
            }],
        }],
    }
    rows = parse_metrics_export(payload)
    assert len(rows) == 2
    names = {r.metric_name for r in rows}
    assert "claude_code.code_edit_tool.decision" in names
    assert "claude_code.lines_of_code.count" in names
    loc_row = next(r for r in rows if "lines_of_code" in r.metric_name)
    assert loc_row.value == 120.0
