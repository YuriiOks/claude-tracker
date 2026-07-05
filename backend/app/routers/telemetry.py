"""Telemetry configuration + OTel event query endpoints.

All routes are mounted under /api (set in main.py).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

import app.db as db_mod
from app.models.otel_event import OtelEventRow
from app.models.otel_metric import OtelMetricRow
from app.schemas.otel import (
    CostByModel,
    CostBySource,
    CostSummary,
    OtelError,
    OtelEvent,
    OtelMetrics,
    OtelSummary,
    TelemetryConfig,
    TelemetryConfigWrite,
    TelemetryExporters,
    TelemetryOptions,
    TelemetryWriteResponse,
    TokensByModel,
    TokensByType,
    TokenSummary,
    ToolLatency,
    fmt_ts,
)
from app.services.telemetry_writer import StaleFile, read_telemetry, write_telemetry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])

_ERROR_EVENT_NAMES = {"api_error", "api_retries_exhausted", "internal_error"}


async def _get_metric_counts(db) -> tuple[int, str | None]:  # noqa: ANN001
    """Return (metric_total, last_metric_at) from otel_metric table."""
    total_row = await db.execute(select(func.count()).select_from(OtelMetricRow))
    metric_total: int = total_row.scalar_one() or 0
    last_row = await db.execute(select(func.max(OtelMetricRow.ts)))
    last_ts: datetime | None = last_row.scalar_one()
    return metric_total, fmt_ts(last_ts)


@router.get("/telemetry", response_model=TelemetryConfig)
async def get_telemetry() -> TelemetryConfig:
    raw = read_telemetry()
    sm = db_mod._sessionmaker
    assert sm is not None

    async with sm() as db:
        total_row = await db.execute(select(func.count()).select_from(OtelEventRow))
        event_total: int = total_row.scalar_one() or 0

        last_row = await db.execute(select(func.max(OtelEventRow.ts)))
        last_ts: datetime | None = last_row.scalar_one()
        last_event_at = fmt_ts(last_ts)

        metric_total, last_metric_at = await _get_metric_counts(db)

    return TelemetryConfig(
        enabled=raw["enabled"],
        ingest_url=raw["ingestUrl"],
        metrics_url=raw["metricsUrl"],
        exporters=TelemetryExporters(
            logs=raw["exporters"]["logs"],
            metrics=raw["exporters"]["metrics"],
        ),
        options=TelemetryOptions(
            log_tool_details=raw["options"]["logToolDetails"],
            log_user_prompts=raw["options"]["logUserPrompts"],
        ),
        settings_path=raw["settingsPath"],
        file_exists=raw["fileExists"],
        mtime=raw["mtime"],
        event_total=event_total,
        last_event_at=last_event_at,
        metric_total=metric_total,
        last_metric_at=last_metric_at,
    )


@router.put("/telemetry", response_model=TelemetryWriteResponse)
async def put_telemetry(body: TelemetryConfigWrite) -> TelemetryWriteResponse:
    try:
        raw = write_telemetry(
            enabled=body.enabled,
            log_tool_details=body.log_tool_details,
            log_user_prompts=body.log_user_prompts,
            endpoint=body.endpoint,
            if_unchanged_since=body.if_unchanged_since,
        )
    except StaleFile as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    sm = db_mod._sessionmaker
    assert sm is not None

    async with sm() as db:
        total_row = await db.execute(select(func.count()).select_from(OtelEventRow))
        event_total: int = total_row.scalar_one() or 0

        last_row = await db.execute(select(func.max(OtelEventRow.ts)))
        last_ts: datetime | None = last_row.scalar_one()
        last_event_at = fmt_ts(last_ts)

        metric_total, last_metric_at = await _get_metric_counts(db)

    return TelemetryWriteResponse(
        enabled=raw["enabled"],
        ingest_url=raw["ingestUrl"],
        metrics_url=raw["metricsUrl"],
        exporters=TelemetryExporters(
            logs=raw["exporters"]["logs"],
            metrics=raw["exporters"]["metrics"],
        ),
        options=TelemetryOptions(
            log_tool_details=raw["options"]["logToolDetails"],
            log_user_prompts=raw["options"]["logUserPrompts"],
        ),
        settings_path=raw["settingsPath"],
        file_exists=raw["fileExists"],
        mtime=raw["mtime"],
        event_total=event_total,
        last_event_at=last_event_at,
        metric_total=metric_total,
        last_metric_at=last_metric_at,
        backup_path=raw.get("backupPath", ""),
    )


@router.get("/otel/events", response_model=list[OtelEvent])
async def get_otel_events(
    n: int = Query(default=200, ge=1, le=2000),
    kind: str = Query(default=""),
) -> list[OtelEvent]:
    """Return recent OTel events, newest first.

    Optional ?kind= filter matches event_name exactly.
    """
    sm = db_mod._sessionmaker
    assert sm is not None

    async with sm() as db:
        q = select(OtelEventRow).order_by(OtelEventRow.ts.desc()).limit(n)
        if kind:
            q = q.where(OtelEventRow.event_name == kind)
        rows = await db.execute(q)
        results = []
        for row in rows.scalars().all():
            try:
                attrs = json.loads(row.attrs) if row.attrs else {}
            except (json.JSONDecodeError, TypeError):
                attrs = {}
            results.append(OtelEvent(
                id=row.id,
                event_name=row.event_name,
                ts=fmt_ts(row.ts) or "",
                session_id=row.session_id,
                prompt_id=row.prompt_id,
                repo=row.repo,
                attrs=attrs,
            ))
    return results


@router.get("/otel/summary", response_model=OtelSummary)
async def get_otel_summary(
    hours: int = Query(default=24, ge=1, le=8760),
) -> OtelSummary:
    """Return aggregated OTel stats for the last `hours` hours."""
    sm = db_mod._sessionmaker
    assert sm is not None

    cutoff = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=hours)

    async with sm() as db:
        # Total count in window
        total_row = await db.execute(
            select(func.count())
            .select_from(OtelEventRow)
            .where(OtelEventRow.ts >= cutoff)
        )
        event_total: int = total_row.scalar_one() or 0

        # Last event timestamp
        last_row = await db.execute(
            select(func.max(OtelEventRow.ts))
            .where(OtelEventRow.ts >= cutoff)
        )
        last_ts: datetime | None = last_row.scalar_one()
        last_event_at = fmt_ts(last_ts)

        # Event counts by name
        counts_rows = await db.execute(
            select(OtelEventRow.event_name, func.count().label("cnt"))
            .where(OtelEventRow.ts >= cutoff)
            .group_by(OtelEventRow.event_name)
        )
        counts: dict[str, int] = {row.event_name: row.cnt for row in counts_rows}

        # Error events (api_error, api_retries_exhausted, internal_error)
        error_rows = await db.execute(
            select(OtelEventRow)
            .where(
                OtelEventRow.ts >= cutoff,
                OtelEventRow.event_name.in_(list(_ERROR_EVENT_NAMES)),
            )
            .order_by(OtelEventRow.ts.desc())
            .limit(50)
        )
        errors: list[OtelError] = []
        for row in error_rows.scalars().all():
            try:
                attrs = json.loads(row.attrs) if row.attrs else {}
            except (json.JSONDecodeError, TypeError):
                attrs = {}
            sc = attrs.get("status_code") or attrs.get("statusCode")
            errors.append(OtelError(
                ts=fmt_ts(row.ts) or "",
                event_name=row.event_name,
                model=attrs.get("model"),
                status_code=int(sc) if sc is not None else None,
                error=attrs.get("error"),
                attempt=attrs.get("attempt"),
            ))

        # Tool latency — from tool_result events
        tool_rows = await db.execute(
            select(OtelEventRow)
            .where(
                OtelEventRow.ts >= cutoff,
                OtelEventRow.event_name == "tool_result",
            )
            .order_by(OtelEventRow.ts.asc())
        )
        tool_data: dict[str, list[float]] = {}
        for row in tool_rows.scalars().all():
            try:
                attrs = json.loads(row.attrs) if row.attrs else {}
            except (json.JSONDecodeError, TypeError):
                attrs = {}
            tool_name = attrs.get("tool_name")
            duration = attrs.get("duration_ms")
            if tool_name and duration is not None:
                try:
                    tool_data.setdefault(str(tool_name), []).append(float(duration))
                except (TypeError, ValueError):
                    pass

    tool_latency: list[ToolLatency] = []
    for tool_name, durations in tool_data.items():
        durations_sorted = sorted(durations)
        count = len(durations_sorted)
        p50 = _percentile(durations_sorted, 50)
        p95 = _percentile(durations_sorted, 95)
        max_ms = max(durations_sorted)
        tool_latency.append(ToolLatency(
            tool=tool_name,
            count=count,
            p50_ms=p50,
            p95_ms=p95,
            max_ms=max_ms,
        ))
    tool_latency.sort(key=lambda x: x.count, reverse=True)

    return OtelSummary(
        window_hours=hours,
        event_total=event_total,
        last_event_at=last_event_at,
        counts=counts,
        errors=errors,
        tool_latency=tool_latency,
    )


def _percentile(sorted_vals: list[float], pct: int) -> float:
    """Compute the p-th percentile of a sorted list using nearest-rank method."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    idx = max(0, math.ceil(n * pct / 100) - 1)
    return sorted_vals[idx]


@router.get("/otel/metrics", response_model=OtelMetrics)
async def get_otel_metrics(
    hours: int = Query(default=24, ge=1, le=87600),
) -> OtelMetrics:
    """Return aggregated OTel metric stats for the last `hours` hours.

    Aggregation rules:
    - kind='sum' (delta): SUM(value) across all rows in the window.
    - kind='gauge': latest value by ts (not yet surfaced in this endpoint's
      top-level fields, but the table supports it).
    - cost/tokens are grouped by attrs.model / attrs.query_source / attrs.type.
    """
    sm = db_mod._sessionmaker
    assert sm is not None

    cutoff = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=hours)

    async with sm() as db:
        # Total metric rows in window.
        total_row = await db.execute(
            select(func.count())
            .select_from(OtelMetricRow)
            .where(OtelMetricRow.ts >= cutoff)
        )
        metric_total: int = total_row.scalar_one() or 0

        # Last metric timestamp.
        last_row = await db.execute(
            select(func.max(OtelMetricRow.ts))
            .where(OtelMetricRow.ts >= cutoff)
        )
        last_ts: datetime | None = last_row.scalar_one()
        last_metric_at = fmt_ts(last_ts)

        # Fetch all relevant metric rows for in-Python aggregation.
        # We handle: cost.usage, token.usage, session.count, active_time.total.
        # Only sum-kind rows are fetched (gauge rows would need different logic).
        rows_result = await db.execute(
            select(OtelMetricRow)
            .where(
                OtelMetricRow.ts >= cutoff,
                OtelMetricRow.kind == "sum",
            )
        )
        all_rows = rows_result.scalars().all()

    # Aggregate in Python — simpler and more flexible than complex SQL.
    cost_total = 0.0
    cost_by_model: dict[str, float] = {}
    cost_by_source: dict[str, float] = {}
    token_total = 0
    tokens_by_type: dict[str, int] = {}
    tokens_by_model: dict[str, int] = {}
    sessions = 0
    active_time_sec = 0.0

    for row in all_rows:
        try:
            attrs = json.loads(row.attrs) if row.attrs else {}
        except (json.JSONDecodeError, TypeError):
            attrs = {}

        val = row.value
        name = row.metric_name

        if name == "claude_code.cost.usage":
            cost_total += val
            model = attrs.get("model")
            if model:
                cost_by_model[model] = cost_by_model.get(model, 0.0) + val
            source = attrs.get("query_source")
            if source:
                cost_by_source[source] = cost_by_source.get(source, 0.0) + val

        elif name == "claude_code.token.usage":
            token_int = int(round(val))
            token_total += token_int
            tok_type = attrs.get("type")
            if tok_type:
                tokens_by_type[tok_type] = tokens_by_type.get(tok_type, 0) + token_int
            model = attrs.get("model")
            if model:
                tokens_by_model[model] = tokens_by_model.get(model, 0) + token_int

        elif name == "claude_code.session.count":
            sessions += int(round(val))

        elif name == "claude_code.active_time.total":
            active_time_sec += val

    # Sort breakdowns by value descending for stable output.
    by_model_cost = sorted(
        [CostByModel(model=m, cost=c) for m, c in cost_by_model.items()],
        key=lambda x: x.cost,
        reverse=True,
    )
    by_source_cost = sorted(
        [CostBySource(query_source=s, cost=c) for s, c in cost_by_source.items()],
        key=lambda x: x.cost,
        reverse=True,
    )
    by_type_tokens = sorted(
        [TokensByType(type=t, tokens=n) for t, n in tokens_by_type.items()],
        key=lambda x: x.tokens,
        reverse=True,
    )
    by_model_tokens = sorted(
        [TokensByModel(model=m, tokens=n) for m, n in tokens_by_model.items()],
        key=lambda x: x.tokens,
        reverse=True,
    )

    return OtelMetrics(
        window_hours=hours,
        cost=CostSummary(
            total=cost_total,
            by_model=by_model_cost,
            by_source=by_source_cost,
        ),
        tokens=TokenSummary(
            total=token_total,
            by_type=by_type_tokens,
            by_model=by_model_tokens,
        ),
        sessions=sessions,
        active_time_sec=active_time_sec,
        metric_total=metric_total,
        last_metric_at=last_metric_at,
    )
