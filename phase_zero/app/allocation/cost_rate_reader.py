"""
Cost Rate Reader — Component 3/10.

Layer: Allocation.

Reads raw.cost_management for the current session_id.
Indexes by region + gpu_pool_id + date for lookup by downstream
components (Type A Builder, Identity Broken Builder, Closure Rule Enforcer).

Runs in parallel with the Telemetry Aggregator → Billing Period Deriver
chain. Both receive session_id from the Run Receiver.

Defense in depth: WHERE session_id = current session filters even though
Ingestion Commit replacement semantics guarantee only one session's rows
are active.

Spec: allocation-engine-design.md — Component 3 — Cost Rate Reader
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
class CostRateRecord:
    """Single cost rate record from raw.cost_management."""

    region: str
    gpu_pool_id: str
    date: date
    reserved_gpu_hours: Decimal
    cost_per_gpu_hour: Decimal


class CostRateResult(BaseModel):
    """Result of the Cost Rate Reader."""

    result: Literal["SUCCESS", "FAIL"]
    records: list[CostRateRecord] = Field(default_factory=list)
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def success(cls, records: list[CostRateRecord]) -> CostRateResult:
        return cls(result="SUCCESS", records=records)

    @classmethod
    def failed(cls, error: str) -> CostRateResult:
        return cls(result="FAIL", error=error)


_READ_SQL = text("""
    SELECT
        region,
        gpu_pool_id,
        date,
        reserved_gpu_hours,
        cost_per_gpu_hour
    FROM raw.cost_management
    WHERE session_id = :sid
""")


def read_cost_rates(
    conn: Connection,
    session_id: UUID,
) -> CostRateResult:
    """
    Read cost rates from raw.cost_management for the given session.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    CostRateResult
        SUCCESS with cost rate records, or FAIL if empty/unreadable.
    """
    try:
        rows = conn.execute(_READ_SQL, {"sid": str(session_id)}).fetchall()

        if not rows:
            return CostRateResult.failed(
                error=f"raw.cost_management unavailable for session {session_id}"
            )

        records = [
            CostRateRecord(
                region=row.region,
                gpu_pool_id=row.gpu_pool_id,
                date=row.date,
                reserved_gpu_hours=row.reserved_gpu_hours,
                cost_per_gpu_hour=row.cost_per_gpu_hour,
            )
            for row in rows
        ]

        records = sorted(
            records,
            key=lambda r: (r.region, r.gpu_pool_id, r.date),
        )

        return CostRateResult.success(records=records)

    except Exception as exc:
        return CostRateResult.failed(
            error=f"Cost rate read failed for session {session_id}: {exc}"
        )
