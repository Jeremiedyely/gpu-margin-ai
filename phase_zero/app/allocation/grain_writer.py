"""
Allocation Grain Writer — Component 9/10.

Layer: Allocation.

Writes all computed grain records atomically to dbo.allocation_grain.
  - Appends session_id to every record
  - Single DB transaction — all written or none (no partial writes)
  - Rollback via DB transaction ROLLBACK, not DELETE (P1 #12)
  - Explicit write timeout (L2 P2 #10)

Implementation contract:
  The atomic write MUST be wrapped in a single DB transaction.
  On any write failure, the transaction ROLLBACK is issued by the DB engine.
  If the ROLLBACK itself fails, the operator must be alerted immediately.

Spec: allocation-engine-design.md — Component 9 — Allocation Grain Writer
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.allocation.cost_revenue_calculator import ComputedRecord


class GrainWriteResult(BaseModel):
    """Result of the Allocation Grain Writer."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    row_count: int = 0
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID, row_count: int) -> GrainWriteResult:
        return cls(result="SUCCESS", session_id=session_id, row_count=row_count)

    @classmethod
    def failed(cls, error: str, session_id: UUID | None = None) -> GrainWriteResult:
        return cls(result="FAIL", error=error, session_id=session_id)


_INSERT_SQL = text("""
    INSERT INTO dbo.allocation_grain (
        session_id, region, gpu_pool_id, date, billing_period,
        allocation_target, unallocated_type, failed_tenant_id,
        gpu_hours, cost_per_gpu_hour, contracted_rate,
        revenue, cogs, gross_margin
    ) VALUES (
        :session_id, :region, :gpu_pool_id, :date, :billing_period,
        :allocation_target, :unallocated_type, :failed_tenant_id,
        :gpu_hours, :cost_per_gpu_hour, :contracted_rate,
        :revenue, :cogs, :gross_margin
    )
""")


def write_allocation_grain(
    conn: Connection,
    session_id: UUID,
    records: list[ComputedRecord],
) -> GrainWriteResult:
    """
    Write computed grain records atomically to dbo.allocation_grain.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection. Caller owns the outer transaction boundary
        for test rollback. This function starts a SAVEPOINT for atomicity.
    session_id : UUID
        Current ingestion session — appended to every row.
    records : list[ComputedRecord]
        Fully computed grain records from Cost & Revenue Calculator.

    Returns
    -------
    GrainWriteResult
        SUCCESS with row_count, or FAIL with error.
    """
    if not records:
        return GrainWriteResult.failed(
            error="No records to write — computed_records is empty",
            session_id=session_id,
        )

    try:
        savepoint = conn.begin_nested()
        try:
            for rec in records:
                conn.execute(
                    _INSERT_SQL,
                    {
                        "session_id": str(session_id),
                        "region": rec.region,
                        "gpu_pool_id": rec.gpu_pool_id,
                        "date": rec.date,
                        "billing_period": rec.billing_period,
                        "allocation_target": rec.allocation_target,
                        "unallocated_type": rec.unallocated_type,
                        "failed_tenant_id": rec.failed_tenant_id,
                        "gpu_hours": rec.gpu_hours,
                        "cost_per_gpu_hour": rec.cost_per_gpu_hour,
                        "contracted_rate": rec.contracted_rate,
                        "revenue": rec.revenue,
                        "cogs": rec.cogs,
                        "gross_margin": rec.gross_margin,
                    },
                )
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            return GrainWriteResult.failed(
                error=(
                    f"allocation_grain write failed — transaction rolled back: "
                    f"{exc} · session_id: {session_id}"
                ),
                session_id=session_id,
            )

        return GrainWriteResult.success(
            session_id=session_id,
            row_count=len(records),
        )

    except Exception as exc:
        return GrainWriteResult.failed(
            error=(
                f"CRITICAL: allocation_grain rollback failed for session "
                f"{session_id} — manual cleanup required before next "
                f"analysis run. Check 3 will produce wrong verdicts until "
                f"orphaned rows are removed. Original error: {exc}"
            ),
            session_id=session_id,
        )
