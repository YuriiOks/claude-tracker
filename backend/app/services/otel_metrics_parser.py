"""Pure OTLP/HTTP-json metrics parser — no DB, no I/O.

Decodes a Claude Code OTLP metrics export payload into a flat list of
ParsedOtelMetric dataclasses. Unknown or malformed records are skipped
with a warning — one bad record must not abort the whole batch.

Wire encoding (verified against claude 2.1.158 capture):
  {resourceMetrics:[{resource:{attributes:[KV]},scopeMetrics:[{scope:...,metrics:[M]}]}]}
  M: {name:"claude_code.cost.usage", unit:"USD", sum:{aggregationTemporality:1,
       isMonotonic:true, dataPoints:[DP]}}  (or "gauge":{dataPoints:[DP]})
  DP: {attributes:[KV], startTimeUnixNano:"<ns>", timeUnixNano:"<ns>",
       asDouble:<number>}  (or asInt:"<str>" for integer values)
  KV:  {key:"...", value:<AnyValue>}

All captured metrics from claude 2.1.158 are monotonic delta sums.
Gauge handling is defensive only. Histogram/exponentialHistogram are skipped.

The _anyvalue decoder is reused from otel_parser to keep the two parsers
in sync — if the wire format changes, only one place needs an update.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.services.otel_parser import _decode_kv_list, _parse_time_unix_nano

logger = logging.getLogger(__name__)

# Metric aggregation kinds we handle. Unknown kinds are skipped.
_HANDLED_KINDS = {"sum", "gauge"}
_SKIP_KINDS = {"histogram", "exponentialHistogram"}


@dataclass
class ParsedOtelMetric:
    metric_name: str        # e.g. "claude_code.cost.usage" (full name, prefix kept)
    ts: datetime            # UTC naive, from timeUnixNano
    start_ts: datetime | None  # UTC naive, from startTimeUnixNano (None if absent)
    unit: str               # e.g. "USD", "tokens", "s", ""
    kind: str               # "sum" or "gauge"
    temporality: int        # 0=unspecified, 1=DELTA, 2=CUMULATIVE (from sum block)
    is_monotonic: bool      # from sum block; False for gauge
    value: float            # asDouble value (never None — parse_dp guards this)
    # Merged resource + dataPoint attributes into one flat dict.
    attrs: dict = field(default_factory=dict)
    # SHA-1 of json.dumps(sorted(attrs.items())) — stable dedup key.
    attrs_key: str = ""


def _attrs_key(attrs: dict) -> str:
    """Compute a stable SHA-1 hash of sorted attribute items for dedup."""
    serialized = json.dumps(sorted(attrs.items()), separators=(",", ":"), default=str)
    return hashlib.sha1(serialized.encode()).hexdigest()  # noqa: S324


def _parse_dp(
    dp: dict,
    resource_attrs: dict,
    metric_name: str,
    unit: str,
    kind: str,
    temporality: int,
    is_monotonic: bool,
) -> ParsedOtelMetric | None:
    """Parse one dataPoint dict into a ParsedOtelMetric.

    Returns None (without raising) if required fields are missing/invalid.
    """
    if not isinstance(dp, dict):
        return None

    # Timestamp — required.
    ts_raw = dp.get("timeUnixNano")
    if ts_raw is None:
        logger.debug("otel_metrics_parser: dataPoint missing timeUnixNano — skipping")
        return None
    ts = _parse_time_unix_nano(ts_raw)
    if ts is None:
        logger.warning("otel_metrics_parser: unparseable timeUnixNano=%r — skipping", ts_raw)
        return None

    # Start timestamp — optional.
    start_ts: datetime | None = None
    start_raw = dp.get("startTimeUnixNano")
    if start_raw is not None:
        start_ts = _parse_time_unix_nano(start_raw)

    # Value — CRITICAL: use membership check, NOT truthiness.
    # asDouble=0 is a valid value (cacheRead=0 tokens) — must NOT fall through.
    if "asDouble" in dp:
        try:
            value = float(dp["asDouble"])
        except (TypeError, ValueError):
            logger.warning("otel_metrics_parser: invalid asDouble=%r — skipping", dp["asDouble"])
            return None
    elif "asInt" in dp:
        # asInt may arrive as a JSON string per the OTLP spec.
        try:
            value = float(int(dp["asInt"]))
        except (TypeError, ValueError):
            logger.warning("otel_metrics_parser: invalid asInt=%r — skipping", dp["asInt"])
            return None
    else:
        logger.debug("otel_metrics_parser: dataPoint has no asDouble/asInt — skipping")
        return None

    # DataPoint-level attributes.
    dp_attrs: dict = {}
    raw_dp_attrs = dp.get("attributes") or []
    if isinstance(raw_dp_attrs, list):
        dp_attrs = _decode_kv_list(raw_dp_attrs)

    # Merge: resource attrs first, dataPoint overrides.
    merged = {**resource_attrs, **dp_attrs}
    key = _attrs_key(merged)

    return ParsedOtelMetric(
        metric_name=metric_name,
        ts=ts,
        start_ts=start_ts,
        unit=unit,
        kind=kind,
        temporality=temporality,
        is_monotonic=is_monotonic,
        value=value,
        attrs=merged,
        attrs_key=key,
    )


def parse_metrics_export(payload: dict) -> list[ParsedOtelMetric]:  # noqa: ANN001
    """Walk resourceMetrics → scopeMetrics → metrics → (sum|gauge).dataPoints.

    Returns a flat list of ParsedOtelMetric, one per dataPoint.
    Skips (with a warning) any metric or dataPoint that is malformed or missing
    required fields. Never raises — one bad batch line should not abort ingestion.
    """
    results: list[ParsedOtelMetric] = []

    resource_metrics = payload.get("resourceMetrics") or []
    if not isinstance(resource_metrics, list):
        logger.warning("otel_metrics_parser: resourceMetrics is not a list — skipping payload")
        return results

    for rm_idx, rm in enumerate(resource_metrics):
        if not isinstance(rm, dict):
            continue

        # Resource-level attributes (host.arch, service.name, …).
        resource_attrs: dict = {}
        resource = rm.get("resource") or {}
        if isinstance(resource, dict):
            raw_res_attrs = resource.get("attributes") or []
            if isinstance(raw_res_attrs, list):
                resource_attrs = _decode_kv_list(raw_res_attrs)

        scope_metrics = rm.get("scopeMetrics") or []
        if not isinstance(scope_metrics, list):
            continue

        for sm_idx, sm in enumerate(scope_metrics):
            if not isinstance(sm, dict):
                continue

            metrics = sm.get("metrics") or []
            if not isinstance(metrics, list):
                continue

            for m_idx, metric in enumerate(metrics):
                try:
                    parsed = _parse_metric(metric, resource_attrs)
                    results.extend(parsed)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "otel_metrics_parser: skipping metric rm[%d].sm[%d].m[%d]: %s",
                        rm_idx, sm_idx, m_idx, exc,
                    )

    return results


def _parse_metric(metric: dict, resource_attrs: dict) -> list[ParsedOtelMetric]:
    """Parse one metric dict (may produce multiple ParsedOtelMetrics, one per DP)."""
    if not isinstance(metric, dict):
        return []

    metric_name = metric.get("name", "")
    if not metric_name:
        logger.debug("otel_metrics_parser: metric missing name — skipping")
        return []

    unit = metric.get("unit") or ""

    # Determine kind (sum / gauge / histogram / ...).
    kind = ""
    kind_block: dict = {}
    for candidate_kind in ("sum", "gauge", "histogram", "exponentialHistogram"):
        if candidate_kind in metric:
            kind = candidate_kind
            kind_block = metric[candidate_kind]
            break

    if not kind:
        logger.debug("otel_metrics_parser: metric %r has no recognized kind — skipping", metric_name)
        return []

    if kind in _SKIP_KINDS:
        logger.debug("otel_metrics_parser: skipping %s metric %r (unsupported kind)", kind, metric_name)
        return []

    if kind not in _HANDLED_KINDS:
        logger.warning("otel_metrics_parser: unknown metric kind %r for %r — skipping", kind, metric_name)
        return []

    if not isinstance(kind_block, dict):
        return []

    # Kind-level metadata.
    temporality = 0
    is_monotonic = False
    if kind == "sum":
        temporality = int(kind_block.get("aggregationTemporality") or 0)
        is_monotonic = bool(kind_block.get("isMonotonic", False))

    data_points = kind_block.get("dataPoints") or []
    if not isinstance(data_points, list):
        return []

    results: list[ParsedOtelMetric] = []
    for dp_idx, dp in enumerate(data_points):
        try:
            parsed_dp = _parse_dp(
                dp,
                resource_attrs,
                metric_name,
                unit,
                kind,
                temporality,
                is_monotonic,
            )
            if parsed_dp is not None:
                results.append(parsed_dp)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "otel_metrics_parser: skipping dataPoint[%d] of %r: %s",
                dp_idx, metric_name, exc,
            )

    return results
