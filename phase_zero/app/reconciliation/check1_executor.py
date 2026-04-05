"""
Check 1 Executor — Capacity vs Usage — Component 1/7.

Layer: Reconciliation.
Grain: Region × GPU Pool × Day.

Per Region × GPU Pool × Day:
  consumed = SUM(raw.telemetry.gpu_hours_consumed)
  reserved = raw.cost_management.reserved_gpu_hours

  IF consumed > reserved for ANY grain → verdict = FAIL
  IF no cost_management row for a telemetry grain → verdict = FAIL
  IF consumed ≤ reserved for ALL grains → verdict = PASS

Both source tables filtered by session_id (defense in depth).

Spec: reconciliation-engine-design.md — Component 1 — Check 1 Executor
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
class Check1FailingRecord:
    """One grain where consumed > reserved."""

    region: str
    gpu_pool_id: str
    date: date
    consumed: Decimal
    reserved: Decimal
    excess: Decimal


class Check1Result(BaseModel):
    """Result of the Check 1 Executor."""

    verdict: Literal["PASS", "FAIL"]
    session_id: UUID | None = None
    failing_count: int | None = None
    failing_records: list[Check1FailingRecord] = Field(default_factory=list)
    detail: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def passed(cls, session_id: UUID) -> Check1Result:
        return cls(verdict="PASS", session_id=session_id)

    @classmethod
    def failed(cls, session_id: UUID, records: list[Check1FailingRecord]) -> Check1Result:
        return cls(
            verdict="FAIL", session_id=session_id,
            failing_count=len(records), failing_records=records,
        )

    @classmethod
    def error(cls, session_id: UUID, detail: str) -> Check1Result:
        return cls(verdict="FAIL", session_id=session_id, detail=detail)


_CONSUMED_SQL = text("""
    SELECT
        region,
        gpu_pool_id,
        date,
        SUM(gpu_hours_consumed) AS consumed
    FROM raw.telemetry
    WHERE session_id = :sid
    GROUP BY region, gpu_pool_id, date
""")

_RESERVED_SQL = text("""
    SELECT
        region,
        gpu_pool_id,
        date,
        reserved_gpu_hours
    FROM raw.cost_management
    WHERE session_id = :sid
""")


def execute_check1(
    conn: Connection,
    session_id: UUID,
) -> Check1Result:
    """
    Execute Check 1: Capacity vs Usage.

    Parameters
    ----------
    conn : Connection
        SQLAlchemy connection (caller owns transaction boundary).
    session_id : UUID
        Current ingestion session.

    Returns
    -------
    Check1Result
        PASS if consumed ≤ reserved for all grains, FAIL otherwise.
    """
    try:
        consumed_rows = conn.execute(_CONSUMED_SQL, {"sid": str(session_id)}).fetchall()
        reserved_rows = conn.execute(_RESERVED_SQL, {"sid": str(session_id)}).fetchall()
    except Exception as exc:
        return Check1Result.error(
            session_id=session_id,
            detail=f"Check 1 could not execute — source unreadable: {exc}",
        )

    if not consumed_rows:
        return Check1Result.error(
            session_id=session_id,
            detail="Check 1 could not execute — raw.telemetry empty for session",
        )

    if not reserved_rows:
        return Check1Result.error(
            session_id=session_id,
            detail="Check 1 could not execute — raw.cost_management empty for session",
        )

    # Build reserved index: (region, gpu_pool_id, date) → reserved_gpu_hours
    reserved_index: dict[tuple[str, str, date], Decimal] = {
        (r.region, r.gpu_pool_id, r.date): r.reserved_gpu_hours
        for r in reserved_rows
    }

    failing: list[Check1FailingRecord] = []

    for row in consumed_rows:
        key = (row.region, row.gpu_pool_id, row.date)
        reserved = reserved_index.get(key)

        if reserved is None:
            failing.append(
                Check1FailingRecord(
                    region=row.region, gpu_pool_id=row.gpu_pool_id,
                    date=row.date, consumed=row.consumed,
                    reserved=Decimal("0"), excess=row.consumed,
                )
            )
            continue

        if row.consumed > reserved:
            failing.append(
                Check1FailingRecord(
                    region=row.region, gpu_pool_id=row.gpu_pool_id,
                    date=row.date, consumed=row.consumed,
                    reserved=reserved, excess=row.consumed - reserved,
                )
            )

    if failing:
        return Check1Result.failed(session_id=session_id, records=failing)

    return Check1Result.passed(session_id=session_id)
