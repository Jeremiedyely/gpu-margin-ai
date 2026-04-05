"""
Reconciliation Result Writer — Component 6/7.

Layer: Reconciliation.

Writes three verdict rows atomically to dbo.reconciliation_results.
All three written or none — no partial writes.

Atomic write via SAVEPOINT (same pattern as AE Grain Writer — P1 #12).

Columns: session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail.

check_order is a DB-layer column (V10 migration) with a bidirectional mapping:
  'Capacity vs Usage'             → 1
  'Usage vs Tenant Mapping'       → 2
  'Computed vs Billed vs Posted'  → 3
Enforced by CHK_recon_check_order_mapping constraint.

Spec: reconciliation-engine-design.md — Component 6 — Result Writer
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.reconciliation.result_aggregator import AggregatedResults


# Bidirectional mapping enforced by CHK_recon_check_order_mapping (V10 migration)
_CHECK_ORDER_MAP: dict[str, int] = {
    "Capacity vs Usage": 1,
    "Usage vs Tenant Mapping": 2,
    "Computed vs Billed vs Posted": 3,
}


class REWriteResult(BaseModel):
    """Result of the Reconciliation Result Writer."""

    result: Literal["SUCCESS", "FAIL"]
    session_id: UUID | None = None
    error: str | None = None

    @classmethod
    def success(cls, session_id: UUID) -> REWriteResult:
        return cls(result="SUCCESS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID | None, error: str) -> REWriteResult:
        return cls(result="FAIL", session_id=session_id, error=error)


_INSERT_SQL = text("""
    INSERT INTO dbo.reconciliation_results
        (session_id, check_name, check_order, verdict, fail_subtype, failing_count, detail)
    VALUES
        (:sid, :check_name, :check_order, :verdict, :fail_subtype, :failing_count, :detail)
""")


def write_reconciliation_results(
    conn: Connection,
    aggregated: AggregatedResults,
    session_id: UUID,
) -> REWriteResult:
    """
    Write reconciliation results atomically.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns outer transaction).
    aggregated : AggregatedResults
        Aggregated result set from Result Aggregator (must be SUCCESS).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    REWriteResult
        SUCCESS if all 3 rows written, FAIL on error.
    """
    if aggregated.result != "SUCCESS":
        return REWriteResult.failed(
            session_id=session_id,
            error=f"reconciliation_results write skipped — "
            f"aggregation result is {aggregated.result}: {aggregated.error}",
        )

    if not aggregated.rows:
        return REWriteResult.failed(
            session_id=session_id,
            error="reconciliation_results write failed — no rows to write",
        )

    try:
        savepoint = conn.begin_nested()
        try:
            for row in aggregated.rows:
                check_order = _CHECK_ORDER_MAP.get(row.check_name)
                if check_order is None:
                    raise ValueError(
                        f"Unknown check_name '{row.check_name}' — "
                        f"no check_order mapping exists"
                    )
                conn.execute(
                    _INSERT_SQL,
                    {
                        "sid": str(session_id),
                        "check_name": row.check_name,
                        "check_order": check_order,
                        "verdict": row.verdict,
                        "fail_subtype": row.fail_subtype,
                        "failing_count": row.failing_count,
                        "detail": row.detail,
                    },
                )
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            return REWriteResult.failed(
                session_id=session_id,
                error=f"reconciliation_results write failed — "
                f"transaction rolled back: {exc} · session_id: {session_id}",
            )
        return REWriteResult.success(session_id=session_id)
    except Exception as exc:
        return REWriteResult.failed(
            session_id=session_id,
            error=f"CRITICAL: reconciliation_results rollback failed — "
            f"data integrity at risk: {exc} · session_id: {session_id}",
        )
