"""Integration tests for OTel metrics ingestion and /api/otel/metrics endpoint.

Uses httpx.AsyncClient with ASGITransport (no real server needed).
The lifespan is NOT triggered -- we init the DB manually via init_db().

Fixture timestamps are FIXED (batch 05: ~2026-05-31T19:34Z). To avoid window
fragility we pass hours=87600 (10 years) so the cutoff is always in the past.

Expected totals from the 3 real batches:
  cost:  0.10187775 USD (batch 05)
  tokens:
    input=3, output=13, cacheRead=0, cacheCreation=27113
    total = 27129
  sessions: 1 (batch 02)
  active_time_sec: 5.76 (batch 07)
  metric_total: 7 rows (5+1+1)
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.db import init_db

FIXTURES = Path(__file__).parent / "fixtures" / "otel"
BATCH_A = FIXTURES / "metrics_sample.json"    # cost + 4 token types (5 rows)
BATCH_B = FIXTURES / "metrics_sample_b.json"  # session.count (1 row)
BATCH_C = FIXTURES / "metrics_sample_c.json"  # active_time (1 row)

# Use a very large hours window so fixed-timestamp fixtures always fall inside.
_HOURS = 87600  # 10 years


@pytest_asyncio.fixture
async def client():
    """AsyncClient with a fresh isolated DB."""
    import app.db as _db_module
    _db_module._engine = None
    _db_module._sessionmaker = None

    await init_db()
    from app.main import create_app
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _post_batch(client, path: Path) -> None:
    body = path.read_bytes()
    res = await client.post(
        "/v1/metrics",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json() == {"partialSuccess": {}}


# ---------------------------------------------------------------------------
# POST /v1/metrics -- basic storage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_metrics_returns_200_partial_success(client):
    res = await client.post(
        "/v1/metrics",
        content=BATCH_A.read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json() == {"partialSuccess": {}}


@pytest.mark.asyncio
async def test_post_metrics_garbage_still_200(client):
    """Garbage body must never cause a 5xx."""
    res = await client.post(
        "/v1/metrics",
        content=b"not json at all !!!",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_post_metrics_empty_body_still_200(client):
    res = await client.post(
        "/v1/metrics",
        content=b'{"resourceMetrics":[]}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/otel/metrics -- aggregated totals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_endpoint_empty_db(client):
    """Empty DB returns zero values."""
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    assert res.status_code == 200
    body = res.json()
    assert body["metricTotal"] == 0
    assert body["sessions"] == 0
    assert body["cost"]["total"] == 0.0
    assert body["tokens"]["total"] == 0


@pytest.mark.asyncio
async def test_metrics_three_batches_correct_totals(client):
    """POST all 3 real batches and verify aggregated totals.

    Expected (sum of per-batch deltas, one row per dataPoint):
      metric_total = 7 (5+1+1)
      cost.total = 0.10187775
      tokens.total = 27129 (3+13+0+27113)
      sessions = 1
      active_time_sec = 5.76
    """
    await _post_batch(client, BATCH_A)
    await _post_batch(client, BATCH_B)
    await _post_batch(client, BATCH_C)

    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    assert res.status_code == 200
    body = res.json()

    assert body["metricTotal"] == 7
    assert body["sessions"] == 1
    assert abs(body["activeTimeSec"] - 5.76) < 1e-6
    assert abs(body["cost"]["total"] - 0.10187775) < 1e-9
    assert body["tokens"]["total"] == 27129


@pytest.mark.asyncio
async def test_metrics_cost_by_model(client):
    await _post_batch(client, BATCH_A)
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    body = res.json()
    by_model = body["cost"]["byModel"]
    assert len(by_model) == 1
    assert by_model[0]["model"] == "claude-sonnet-4-6"
    assert abs(by_model[0]["cost"] - 0.10187775) < 1e-9


@pytest.mark.asyncio
async def test_metrics_cost_by_source(client):
    await _post_batch(client, BATCH_A)
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    body = res.json()
    by_source = body["cost"]["bySource"]
    assert len(by_source) == 1
    assert by_source[0]["querySource"] == "main"
    assert abs(by_source[0]["cost"] - 0.10187775) < 1e-9


@pytest.mark.asyncio
async def test_metrics_tokens_by_type(client):
    """Token breakdown must include cacheRead=0 -- the falsy-zero trap."""
    await _post_batch(client, BATCH_A)
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    body = res.json()
    by_type = {item["type"]: item["tokens"] for item in body["tokens"]["byType"]}
    assert by_type["input"] == 3
    assert by_type["output"] == 13
    assert "cacheRead" in by_type, "cacheRead=0 row must be stored and aggregated"
    assert by_type["cacheRead"] == 0
    assert by_type["cacheCreation"] == 27113


@pytest.mark.asyncio
async def test_metrics_tokens_by_model(client):
    await _post_batch(client, BATCH_A)
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    body = res.json()
    by_model = body["tokens"]["byModel"]
    assert len(by_model) == 1
    assert by_model[0]["model"] == "claude-sonnet-4-6"
    assert by_model[0]["tokens"] == 27129


# ---------------------------------------------------------------------------
# Dedup -- re-POST all 3 batches; totals must stay unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repost_all_batches_dedup_totals_unchanged(client):
    """Re-POSTing all 3 batches (true resend) must NOT inflate any total.

    The unique constraint (metric_name, attrs_key, start_ts, ts) must make
    all re-inserted rows conflict and be silently ignored.
    """
    # First POST
    for path in (BATCH_A, BATCH_B, BATCH_C):
        await _post_batch(client, path)

    res1 = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    totals_1 = res1.json()

    # Re-POST (simulate Claude's exporter re-sending the same batch)
    for path in (BATCH_A, BATCH_B, BATCH_C):
        await _post_batch(client, path)

    res2 = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    totals_2 = res2.json()

    assert totals_2["metricTotal"] == totals_1["metricTotal"] == 7
    assert totals_2["tokens"]["total"] == totals_1["tokens"]["total"] == 27129
    assert abs(totals_2["cost"]["total"] - totals_1["cost"]["total"]) < 1e-12
    assert totals_2["sessions"] == totals_1["sessions"] == 1
    assert abs(totals_2["activeTimeSec"] - totals_1["activeTimeSec"]) < 1e-9


# ---------------------------------------------------------------------------
# GET /api/telemetry -- evolved shape includes metric fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telemetry_shape_includes_metric_fields(client):
    res = await client.get("/api/telemetry")
    assert res.status_code == 200
    body = res.json()
    assert "metricTotal" in body
    assert isinstance(body["metricTotal"], int)
    # lastMetricAt is null when no metrics ingested yet
    assert "lastMetricAt" in body
    # metricsUrl must be present
    assert "metricsUrl" in body
    assert isinstance(body["metricsUrl"], str)
    # exporters.metrics present
    assert "exporters" in body
    assert "metrics" in body["exporters"]


@pytest.mark.asyncio
async def test_telemetry_metric_total_updates_after_ingest(client):
    await _post_batch(client, BATCH_A)
    res = await client.get("/api/telemetry")
    body = res.json()
    assert body["metricTotal"] == 5  # batch A has 5 datapoints
    assert body["lastMetricAt"] is not None


# ---------------------------------------------------------------------------
# Response schema -- camelCase keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_otel_metrics_response_is_camelcase(client):
    await _post_batch(client, BATCH_A)
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    body = res.json()
    # Top-level camelCase keys from the contract
    assert "windowHours" in body
    assert "activeTimeSec" in body
    assert "metricTotal" in body
    assert "lastMetricAt" in body
    # Nested camelCase
    assert "byModel" in body["cost"]
    assert "bySource" in body["cost"]
    assert "byType" in body["tokens"]
    assert "byModel" in body["tokens"]
    # bySource items
    if body["cost"]["bySource"]:
        assert "querySource" in body["cost"]["bySource"][0]


# ---------------------------------------------------------------------------
# Delta model -- two export intervals must SUM, not overwrite or dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_same_metric_two_intervals_sum(client):
    """Two delta dataPoints for the same metric + attrs across different export
    intervals must produce two stored rows whose values SUM (not be overwritten,
    not be averaged, not be deduped to one row).

    The unique dedup key is (metric_name, attrs_key, start_ts, ts). The two DPs
    below share metric_name and attrs_key but have DISTINCT (start_ts, ts) pairs
    --- one second apart --- so they are two independent delta windows that must
    sum to 7.5.

    Timestamps are synthetic, kept within the 10-year _HOURS window by anchoring
    near the real fixture era (~2026-05-31T19:34Z, ns base 1780256082340000000).
    """
    import json  # noqa: PLC0415 -- intentional local import for clarity

    # Synthetic OTLP payload: metric claude_code.active_time.total, two dataPoints.
    # DP1: interval [T+0 .. T+1], value=3.0
    # DP2: interval [T+1 .. T+2], value=4.5  (start_ts and ts each +1 s = +1_000_000_000 ns)
    # Identical attributes in both DPs → identical attrs_key → dedup key differs only
    # in start_ts/ts. Expected aggregate: 3.0 + 4.5 = 7.5.
    _BASE_NS = 1780256082340000000  # anchors near real fixture era (always inside _HOURS window)
    _INTERVAL_NS = 1_000_000_000   # 1 second in nanoseconds

    _ATTRS = [
        {"key": "user.id",            "value": {"stringValue": "user_synth"}},
        {"key": "session.id",         "value": {"stringValue": "synth-0000-0000-0000-000000000000"}},
        {"key": "terminal.type",      "value": {"stringValue": "test"}},
    ]

    synthetic_payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "scope": {"name": "com.anthropic.claude_code", "version": "synthetic"},
                "metrics": [{
                    "name": "claude_code.active_time.total",
                    "unit": "s",
                    "sum": {
                        "aggregationTemporality": 1,
                        "isMonotonic": True,
                        "dataPoints": [
                            {
                                "attributes": _ATTRS,
                                "startTimeUnixNano": str(_BASE_NS),
                                "timeUnixNano":      str(_BASE_NS + _INTERVAL_NS),
                                "asDouble": 3.0,
                            },
                            {
                                "attributes": _ATTRS,
                                "startTimeUnixNano": str(_BASE_NS + _INTERVAL_NS),
                                "timeUnixNano":      str(_BASE_NS + 2 * _INTERVAL_NS),
                                "asDouble": 4.5,
                            },
                        ],
                    },
                }],
            }],
        }],
    }

    body_bytes = json.dumps(synthetic_payload).encode()

    # First POST: both delta intervals ingested → 2 rows stored.
    res = await client.post(
        "/v1/metrics",
        content=body_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json() == {"partialSuccess": {}}

    # GET: both rows must SUM to 7.5 (not 4.5 overwrite, not 3.75 average).
    res = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    assert res.status_code == 200
    agg = res.json()
    assert abs(agg["activeTimeSec"] - 7.5) < 1e-9, (
        f"Expected 7.5 (sum of two delta intervals), got {agg['activeTimeSec']}"
    )
    # Two distinct rows stored (not collapsed into one).
    assert agg["metricTotal"] == 2, (
        f"Expected 2 rows (one per interval), got {agg['metricTotal']}"
    )

    # Re-POST the SAME payload (true resend simulation).
    # Dedup must hold: (metric_name, attrs_key, start_ts, ts) is identical for each DP
    # on a true resend → INSERT OR IGNORE → no new rows → aggregate unchanged.
    res2 = await client.post(
        "/v1/metrics",
        content=body_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res2.status_code == 200

    res3 = await client.get(f"/api/otel/metrics?hours={_HOURS}")
    agg2 = res3.json()
    assert abs(agg2["activeTimeSec"] - 7.5) < 1e-9, (
        f"Re-POST inflated aggregate: expected 7.5, got {agg2['activeTimeSec']}"
    )
    assert agg2["metricTotal"] == 2, (
        f"Re-POST added rows: expected 2, got {agg2['metricTotal']}"
    )
