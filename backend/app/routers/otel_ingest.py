"""OTLP/HTTP-json receiver for Claude Code telemetry.

These routes are mounted WITHOUT an /api prefix — they must match the
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT configured in settings.json exactly.

  POST /v1/logs    — accepts OTLP LogsService.Export, decodes, stores.
  POST /v1/metrics — Phase-1 no-op stub; returns 200 (Phase 3 TODO).

Safety contract: ALWAYS return HTTP 200 on /v1/logs. If we return 4xx/5xx
Claude's OTel SDK will retry indefinitely and storm our own server.
"""
from __future__ import annotations

import json
import logging
import zlib

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import app.db as db_mod
from app.models.otel_event import OtelEventRow
from app.models.otel_metric import OtelMetricRow
from app.models.session_summary import SessionSummaryRow
from app.services.otel_metrics_parser import ParsedOtelMetric, parse_metrics_export
from app.services.otel_parser import ParsedOtelEvent, parse_logs_export

logger = logging.getLogger(__name__)

router = APIRouter(tags=["otel-ingest"])

_PARTIAL_SUCCESS = json.dumps({"partialSuccess": {}}).encode()

# Caps against oversized/decompression-bomb payloads. Claude Code's own
# exports are tiny (a handful of KB); these limits are generous headroom.
_MAX_BODY_BYTES = 256 * 1024
_MAX_DECOMPRESSED_BYTES = 4 * 1024 * 1024
_GZIP_CHUNK = 64 * 1024


async def _read_capped_body(request: Request, label: str) -> bytes | None:
    """Read the request body, rejecting anything over `_MAX_BODY_BYTES`.

    Checks the declared Content-Length first (cheap early-out), then the
    actual read size (Content-Length can be absent or wrong). Returns
    None if the cap is exceeded.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_BODY_BYTES:
                logger.warning(
                    "otel_ingest %s: content-length %s exceeds %d-byte cap, dropping",
                    label, content_length, _MAX_BODY_BYTES,
                )
                return None
        except ValueError:
            pass
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        logger.warning(
            "otel_ingest %s: body %d bytes exceeds %d-byte cap, dropping",
            label, len(body), _MAX_BODY_BYTES,
        )
        return None
    return body


def _decompress_capped(body: bytes, label: str) -> bytes | None:
    """Gzip-decompress `body`, aborting if output would exceed
    `_MAX_DECOMPRESSED_BYTES` (defends against a decompression bomb rather
    than trusting `gzip.decompress` to materialize the whole thing).
    """
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = bytearray()
    try:
        for i in range(0, len(body), _GZIP_CHUNK):
            remaining = _MAX_DECOMPRESSED_BYTES - len(out) + 1
            out.extend(decompressor.decompress(body[i : i + _GZIP_CHUNK], remaining))
            if len(out) > _MAX_DECOMPRESSED_BYTES:
                logger.warning(
                    "otel_ingest %s: decompressed payload exceeds %d-byte cap, dropping",
                    label, _MAX_DECOMPRESSED_BYTES,
                )
                return None
        out.extend(decompressor.flush())
    except zlib.error as exc:
        logger.warning("otel_ingest %s: gzip decode failed: %s", label, exc)
        return None
    if len(out) > _MAX_DECOMPRESSED_BYTES:
        logger.warning(
            "otel_ingest %s: decompressed payload exceeds %d-byte cap, dropping",
            label, _MAX_DECOMPRESSED_BYTES,
        )
        return None
    return bytes(out)


async def _resolve_repo(session_id: str) -> str | None:
    """Best-effort: look up repo from session_summary table."""
    sm = db_mod._sessionmaker
    if sm is None:
        return None
    try:
        async with sm() as db:
            row = await db.execute(
                select(SessionSummaryRow.repo).where(
                    SessionSummaryRow.session_id == session_id
                )
            )
            return row.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.debug("otel_ingest: repo lookup failed for %s: %s", session_id, exc)
    return None


def _metric_to_row_dict(metric: ParsedOtelMetric, repo: str | None = None) -> dict:
    # Best-effort repo backfill: merge resolved repo into stored attrs (not into
    # attrs_key — key is computed pre-backfill in the parser so dedup stays stable).
    attrs = metric.attrs
    if repo is not None:
        attrs = {**attrs, "_resolved_repo": repo}
    return {
        "metric_name": metric.metric_name,
        "ts": metric.ts,
        "start_ts": metric.start_ts,
        "unit": metric.unit,
        "kind": metric.kind,
        "temporality": metric.temporality,
        "is_monotonic": metric.is_monotonic,
        "value": metric.value,
        "attrs": json.dumps(attrs, default=str),
        "attrs_key": metric.attrs_key,  # unchanged — computed before repo lookup
    }


def _event_to_row_dict(event: ParsedOtelEvent, repo: str | None) -> dict:
    return {
        "event_name": event.event_name,
        "ts": event.ts,
        "session_id": event.session_id,
        "prompt_id": event.prompt_id,
        "event_sequence": event.event_sequence,
        "repo": repo,
        "attrs": json.dumps(event.attrs, default=str),
    }


@router.post("/v1/logs", include_in_schema=False)
async def receive_logs(request: Request) -> Response:
    """Accept OTLP http/json logs export from Claude Code.

    Decodes optional gzip, parses logRecords, bulk-inserts into otel_event
    using INSERT OR IGNORE (via on_conflict_do_nothing) for idempotent
    re-export dedup. Always returns 200.
    """
    try:
        body = await _read_capped_body(request, "/v1/logs")
        if body is None:
            return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)
        enc = request.headers.get("content-encoding", "")
        if enc == "gzip":
            decompressed = _decompress_capped(body, "/v1/logs")
            if decompressed is None:
                return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)
            body = decompressed

        payload = json.loads(body)
        events = parse_logs_export(payload)

        if events:
            # Group events by session_id for repo backfill to avoid N+1.
            session_ids = {e.session_id for e in events if e.session_id}
            repo_map: dict[str, str | None] = {}
            for sid in session_ids:
                repo_map[sid] = await _resolve_repo(sid)

            rows = [
                _event_to_row_dict(evt, repo_map.get(evt.session_id or ""))
                for evt in events
            ]

            sm = db_mod._sessionmaker
            if sm is not None:
                async with sm() as db:
                    stmt = (
                        sqlite_insert(OtelEventRow)
                        .values(rows)
                        .on_conflict_do_nothing(
                            index_elements=["session_id", "event_sequence"]
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()

            logger.info("otel_ingest: stored up to %d events (dedup applied)", len(rows))

    except Exception as exc:  # noqa: BLE001
        # Never fail — Claude's exporter will retry-storm if we 5xx.
        logger.warning("otel_ingest /v1/logs error (still returning 200): %s", exc)

    return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)


@router.post("/v1/metrics", include_in_schema=False)
async def receive_metrics(request: Request) -> Response:
    """Accept OTLP http/json metrics export from Claude Code.

    Decodes optional gzip, parses dataPoints from sum/gauge metrics, bulk-inserts
    into otel_metric using INSERT OR IGNORE (on_conflict_do_nothing) for idempotent
    re-export dedup. Always returns 200.
    """
    try:
        body = await _read_capped_body(request, "/v1/metrics")
        if body is None:
            return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)
        enc = request.headers.get("content-encoding", "")
        if enc == "gzip":
            decompressed = _decompress_capped(body, "/v1/metrics")
            if decompressed is None:
                return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)
            body = decompressed

        payload = json.loads(body)
        metrics = parse_metrics_export(payload)

        if metrics:
            # Best-effort repo backfill by session.id (same pattern as logs path).
            session_ids = {
                m.attrs.get("session.id")
                for m in metrics
                if m.attrs.get("session.id")
            }
            repo_map: dict[str, str | None] = {}
            for sid in session_ids:
                repo_map[sid] = await _resolve_repo(str(sid))

            rows = [
                _metric_to_row_dict(m, repo_map.get(str(m.attrs.get("session.id", ""))))
                for m in metrics
            ]

            sm = db_mod._sessionmaker
            if sm is not None:
                async with sm() as db:
                    stmt = (
                        sqlite_insert(OtelMetricRow)
                        .values(rows)
                        .on_conflict_do_nothing(
                            index_elements=["metric_name", "attrs_key", "start_ts", "ts"]
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()

            logger.info("otel_ingest: stored up to %d metric datapoints (dedup applied)", len(rows))

    except Exception as exc:  # noqa: BLE001
        # Never fail — Claude's exporter will retry-storm if we 5xx.
        logger.warning("otel_ingest /v1/metrics error (still returning 200): %s", exc)

    return Response(content=_PARTIAL_SUCCESS, media_type="application/json", status_code=200)
