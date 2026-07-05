"""Pydantic schemas for OTel endpoints — camelCase wire format mirrors contract."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )


class OtelEvent(_CamelModel):
    """One row from otel_event, serialized for GET /api/otel/events."""
    id: int
    event_name: str
    ts: str  # ISO 8601 with ms + Z: "2026-05-31T18:26:05.566Z"
    session_id: str | None = None
    prompt_id: str | None = None
    repo: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class ToolLatency(_CamelModel):
    """Per-tool latency aggregates from tool_result events."""
    tool: str
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


class OtelError(_CamelModel):
    """One error event from api_error / api_retries_exhausted / internal_error."""
    ts: str  # ISO 8601 ms+Z
    event_name: str
    model: str | None = None
    status_code: int | None = None
    error: str | None = None
    attempt: int | None = None


class OtelSummary(_CamelModel):
    """Aggregated view for GET /api/otel/summary."""
    window_hours: int
    event_total: int
    last_event_at: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    errors: list[OtelError] = Field(default_factory=list)
    tool_latency: list[ToolLatency] = Field(default_factory=list)


class TelemetryOptions(_CamelModel):
    log_tool_details: bool = False
    log_user_prompts: bool = False


class TelemetryExporters(BaseModel):
    logs: str | None = None
    metrics: str | None = None


class TelemetryConfig(_CamelModel):
    """Response shape for GET/PUT /api/telemetry."""
    enabled: bool
    ingest_url: str
    metrics_url: str = ""
    exporters: TelemetryExporters
    options: TelemetryOptions
    settings_path: str
    file_exists: bool
    mtime: float
    event_total: int = 0
    last_event_at: str | None = None
    metric_total: int = 0
    last_metric_at: str | None = None


# ---------------------------------------------------------------------------
# OTel Metrics — GET /api/otel/metrics
# ---------------------------------------------------------------------------


class CostByModel(_CamelModel):
    model: str
    cost: float


class CostBySource(_CamelModel):
    query_source: str
    cost: float


class CostSummary(_CamelModel):
    total: float
    by_model: list[CostByModel] = Field(default_factory=list)
    by_source: list[CostBySource] = Field(default_factory=list)


class TokensByType(_CamelModel):
    type: str
    tokens: int


class TokensByModel(_CamelModel):
    model: str
    tokens: int


class TokenSummary(_CamelModel):
    total: int
    by_type: list[TokensByType] = Field(default_factory=list)
    by_model: list[TokensByModel] = Field(default_factory=list)


class OtelMetrics(_CamelModel):
    """Aggregated metrics view for GET /api/otel/metrics."""
    window_hours: int
    cost: CostSummary
    tokens: TokenSummary
    sessions: int
    active_time_sec: float
    metric_total: int
    last_metric_at: str | None = None


class TelemetryConfigWrite(_CamelModel):
    """Request body for PUT /api/telemetry."""
    enabled: bool
    log_tool_details: bool = False
    log_user_prompts: bool = False
    endpoint: str | None = None
    if_unchanged_since: float | None = None


class TelemetryWriteResponse(TelemetryConfig):
    """GET-shape plus backupPath."""
    backup_path: str = ""


# Helper to format a UTC-naive datetime as ISO with ms + "Z".
def fmt_ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
