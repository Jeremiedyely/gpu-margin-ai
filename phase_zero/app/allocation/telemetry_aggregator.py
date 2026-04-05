"""
Telemetry Aggregator — Component 1/10.

Layer: Allocation.

Reads raw.telemetry for the current session_id under snapshot isolation.
Groups by tenant_id + region + gpu_pool_id + date.
Computes: gpu_hours = SUM(gpu_hours_consumed).

Defense in depth: WHERE session_id = current session filters even though
Ingestion Commit replacement semantics guarantee only one session's rows
are active.

Spec: allocation-engine-design.md — Component 1 — Telemetry Aggregator
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text


@dataclass(frozen=True)
class TelemetryAggregatedRecord:
    """Single aggregated telemetry record at grain dimensions."""

    tenant_id: str
    region: str
    gpu_pool_id: str
    date: date
    gpu_hours: Decimal


class AggregatorResult(BaseModel):
    """Result of the Telemetry Aggregator."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[TelemetryAggregatedRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[TelemetryAggregatedRecord]) -> AggregatorResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> AggregatorResult:
        return cls(result="FAIL", error=error)


_AGGREGATE_SQL = text("""
    SELECT
        tenant_id,
        region,
        gpu_pool_id,
        date,
        SUM(gpu_hours_consumed) AS gpu_hours
    FROM raw.telemetry
    WHERE session_id = :sid
    GROUP BY tenant_id, region, gpu_pool_id, date
""")


def aggregate_telemetry(
    conn: Connection,
    session_id: UUID,
) -> AggregatorResult:
    """
    Aggregate raw.telemetry by grain dimensions for the given session.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    AggregatorResult
        SUCCESS with aggregated records, or FAIL if no rows found.
    """
    try:
        rows = conn.execute(_AGGREGATE_SQL, {"sid": str(session_id)}).fetchall()

        if not rows:
            return AggregatorResult.failed(
                error=f"raw.telemetry contains no rows for session {session_id}"
            )

        records = [
            TelemetryAggregatedRecord(
                tenant_id=row.tenant_id,
                region=row.region,
                gpu_pool_id=row.gpu_pool_id,
                date=row.date,
                gpu_hours=row.gpu_hours,
            )
            for row in rows
        ]

        records = sorted(
            records,
            key=lambda r: (r.tenant_id, r.region, r.gpu_pool_id, r.date),
        )

        return AggregatorResult.success(records=records)

    except Exception as exc:
        return AggregatorResult.failed(
            error=f"Telemetry aggregation failed for session {session_id}: {exc}"
        )
