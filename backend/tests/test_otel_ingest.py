"""Integration tests for the OTLP ingest endpoints and OTel summary API.

Uses httpx.AsyncClient with ASGITransport (no real server needed).
The lifespan is NOT triggered — we init the DB manually in each test.

Synthetic tool_result / api_error fixture:
  Built to the same VERIFIED wire encoding as the real capture, but uses
  now()-relative timestamps so summary?hours=24 always includes them.
  Clearly marked as synthetic throughout.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.db import init_db

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "otel" / "logs_sample.json"


def _make_synthetic_payload(events: list[dict]) -> dict:
    """Wrap synthetic logRecords in the verified OTLP envelope structure."""
    return {
        "resourceLogs": [{
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "claude-code"}},
                    {"key": "service.version", "value": {"stringValue": "2.1.158"}},
                ]
            },
            "scopeLogs": [{
                "scope": {"name": "com.anthropic.claude_code.events", "version": "2.1.158"},
                "logRecords": events,
            }],
        }],
    }


def _ns_from_dt(dt: datetime) -> str:
    """Convert a datetime to a nanosecond timestamp string."""
    return str(int(dt.timestamp() * 1e9))


@pytest.fixture
def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def make_synthetic_events(now_utc: datetime) -> dict:
    """Synthetic payload with tool_result + api_error events (now-relative).

    SYNTHETIC — not from a real capture. Follows the same OTLP wire encoding
    verified against claude 2.1.158 but uses fictional session/prompt IDs and
    now()-relative timestamps so the summary window always includes them.
    """
    base_ts = now_utc - timedelta(minutes=5)
    session = "synth-session-0000-0000-0000-000000000001"
    prompt = "synth-prompt-0000-0000-0000-000000000001"

    tool_result_rec = {
        "timeUnixNano": _ns_from_dt(base_ts),
        "observedTimeUnixNano": _ns_from_dt(base_ts),
        "body": {"stringValue": "claude_code.tool_result"},
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "tool_result"}},
            {"key": "session.id", "value": {"stringValue": session}},
            {"key": "prompt.id", "value": {"stringValue": prompt}},
            {"key": "event.sequence", "value": {"intValue": 201}},
            {"key": "event.timestamp", "value": {"stringValue": "2099-01-01T00:00:00.000Z"}},
            {"key": "tool_name", "value": {"stringValue": "Bash"}},
            {"key": "tool_use_id", "value": {"stringValue": "toolu_synth_01"}},
            {"key": "success", "value": {"boolValue": True}},
            {"key": "duration_ms", "value": {"intValue": 350}},
        ],
        "droppedAttributesCount": 0,
    }

    api_error_rec = {
        "timeUnixNano": _ns_from_dt(base_ts + timedelta(seconds=1)),
        "observedTimeUnixNano": _ns_from_dt(base_ts + timedelta(seconds=1)),
        "body": {"stringValue": "claude_code.api_error"},
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "api_error"}},
            {"key": "session.id", "value": {"stringValue": session}},
            {"key": "prompt.id", "value": {"stringValue": prompt}},
            {"key": "event.sequence", "value": {"intValue": 202}},
            {"key": "event.timestamp", "value": {"stringValue": "2099-01-01T00:00:01.000Z"}},
            {"key": "model", "value": {"stringValue": "claude-sonnet-4-6"}},
            {"key": "status_code", "value": {"intValue": 429}},
            {"key": "error", "value": {"stringValue": "Too Many Requests"}},
            {"key": "attempt", "value": {"intValue": 1}},
        ],
        "droppedAttributesCount": 0,
    }

    return _make_synthetic_payload([tool_result_rec, api_error_rec])


@pytest_asyncio.fixture
async def client():
    """AsyncClient with a fresh isolated DB (conftest.py autouse resets settings).

    Resets the engine globals so each test gets its own DB at the path that
    conftest's _isolated_db fixture configured via DB_PATH env var.
    """
    import app.db as _db_module
    _db_module._engine = None
    _db_module._sessionmaker = None

    await init_db()
    from app.main import create_app
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# POST /v1/logs — real fixture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_logs_fixture_returns_200(client):
    body = FIXTURE_PATH.read_bytes()
    res = await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})
    assert res.status_code == 200
    assert res.json() == {"partialSuccess": {}}


@pytest.mark.asyncio
async def test_post_logs_fixture_creates_rows(client):
    body = FIXTURE_PATH.read_bytes()
    await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})

    # Verify rows via the events endpoint.
    res = await client.get("/api/otel/events?n=100")
    assert res.status_code == 200
    events = res.json()
    assert len(events) == 4
    names = {e["eventName"] for e in events}
    assert "api_request" in names
    assert "mcp_server_connection" in names


@pytest.mark.asyncio
async def test_post_logs_fixture_dedup_on_repost(client):
    """Re-POSTing the same batch must NOT create duplicate rows."""
    body = FIXTURE_PATH.read_bytes()
    await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})
    await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})

    res = await client.get("/api/otel/events?n=1000")
    assert res.status_code == 200
    events = res.json()
    # Still exactly 4, not 8.
    assert len(events) == 4


@pytest.mark.asyncio
async def test_post_logs_garbage_body_still_200(client):
    """Garbage body must NOT cause a 5xx — always 200."""
    res = await client.post(
        "/v1/logs",
        content=b"not json at all !!!",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_post_logs_empty_body_still_200(client):
    res = await client.post("/v1/logs", content=b"{}", headers={"Content-Type": "application/json"})
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# POST /v1/metrics — no-op stub
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_metrics_stub_200(client):
    res = await client.post(
        "/v1/metrics",
        content=b'{"resourceMetrics":[]}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json() == {"partialSuccess": {}}


# ---------------------------------------------------------------------------
# GET /api/otel/events — filter by kind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_otel_events_kind_filter(client):
    body = FIXTURE_PATH.read_bytes()
    await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})

    res = await client.get("/api/otel/events?kind=api_request")
    assert res.status_code == 200
    events = res.json()
    assert len(events) == 1
    assert events[0]["eventName"] == "api_request"


@pytest.mark.asyncio
async def test_get_otel_events_attrs_contain_cost_usd(client):
    """api_request attrs must include cost_usd as a float (doubleValue decoded)."""
    body = FIXTURE_PATH.read_bytes()
    await client.post("/v1/logs", content=body, headers={"Content-Type": "application/json"})

    res = await client.get("/api/otel/events?kind=api_request")
    ev = res.json()[0]
    assert "cost_usd" in ev["attrs"]
    assert isinstance(ev["attrs"]["cost_usd"], float)


# ---------------------------------------------------------------------------
# GET /api/otel/summary — from synthetic fixture (now-relative timestamps)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_otel_summary_with_synthetic_events(client, now_utc):
    """Synthetic tool_result + api_error events populate summary correctly.

    SYNTHETIC — uses now()-relative timestamps so hours=24 always includes them.
    """
    payload = make_synthetic_events(now_utc)
    body_bytes = json.dumps(payload).encode()
    await client.post("/v1/logs", content=body_bytes, headers={"Content-Type": "application/json"})

    res = await client.get("/api/otel/summary?hours=24")
    assert res.status_code == 200
    summary = res.json()

    assert summary["windowHours"] == 24
    assert summary["eventTotal"] == 2

    counts = summary["counts"]
    assert counts.get("tool_result") == 1
    assert counts.get("api_error") == 1

    # api_error should appear in errors list
    errors = summary["errors"]
    assert len(errors) == 1
    err = errors[0]
    assert err["eventName"] == "api_error"
    assert err["statusCode"] == 429
    assert err["error"] == "Too Many Requests"

    # tool_result for Bash should appear in toolLatency
    latency = summary["toolLatency"]
    assert len(latency) == 1
    assert latency[0]["tool"] == "Bash"
    assert latency[0]["count"] == 1
    assert latency[0]["p50Ms"] == 350.0


@pytest.mark.asyncio
async def test_otel_summary_empty_db(client):
    """Empty DB returns zeros and empty lists."""
    res = await client.get("/api/otel/summary?hours=24")
    assert res.status_code == 200
    s = res.json()
    assert s["eventTotal"] == 0
    assert s["lastEventAt"] is None
    assert s["counts"] == {}
    assert s["errors"] == []
    assert s["toolLatency"] == []


# ---------------------------------------------------------------------------
# GET /api/telemetry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_telemetry_returns_shape(client):
    res = await client.get("/api/telemetry")
    assert res.status_code == 200
    body = res.json()
    assert "enabled" in body
    assert "ingestUrl" in body
    assert "eventTotal" in body
    assert isinstance(body["eventTotal"], int)
