"""OTel metric rows — one row per dataPoint received from Claude Code's OTLP metrics exporter.

Each OTLP delta metric dataPoint becomes one row. The unique constraint
(metric_name, attrs_key, start_ts, ts) provides idempotent dedup:
  - True resend (same export): all four fields match → conflict → ignored.
  - Different export interval (same session, next 10-s tick): ts advances → new row.
    All rows SUM correctly because each covers a disjoint delta window.
"""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OtelMetricRow(Base):
    __tablename__ = "otel_metric"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # UTC-naive datetimes (timezone stripped after conversion from nanoseconds).
    ts: Mapped[object] = mapped_column(DateTime, nullable=False, index=True)
    start_ts: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    unit: Mapped[str] = mapped_column(String, nullable=False, default="")
    # 'sum' or 'gauge' — drives aggregation logic (SUM vs. latest-value).
    kind: Mapped[str] = mapped_column(String, nullable=False, default="sum")
    # OTLP aggregationTemporality int (1=DELTA, 2=CUMULATIVE). 0 if absent (gauge).
    temporality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_monotonic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    # All merged resource + dataPoint attributes as a JSON string.
    attrs: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # SHA-1 of sorted attrs items — stable dedup key independent of insertion order.
    attrs_key: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "metric_name", "attrs_key", "start_ts", "ts",
            name="uq_otel_metric_dedup",
        ),
    )
